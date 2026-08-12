<template>
  <div class="inline-product-match d-flex align-center ga-1" style="min-width:240px">
    <!-- Status badge: auto (green) / suggest (amber) / create (grey) -->
    <v-tooltip :text="statusTooltip" location="top">
      <template #activator="{ props: tip }">
        <v-icon v-bind="tip" :color="statusColor" :icon="statusIcon" size="18" class="flex-shrink-0" />
      </template>
    </v-tooltip>

    <!-- Perf (lazy matcher): when NOT active, render a lightweight read-only field
         instead of the heavy v-autocomplete (menu + virtual list + tooltips). The
         real autocomplete only mounts once the user focuses/clicks this row. On
         initial render of N rows, ZERO v-autocomplete instances mount. -->
    <v-text-field
      v-if="!active"
      :model-value="displayName"
      readonly
      density="compact"
      variant="outlined"
      hide-details
      :disabled="disabled"
      :placeholder="displayName ? '' : 'Начните вводить наименование...'"
      class="flex-grow-1 inline-match-lazy"
      style="min-width:200px"
      @focus="activate"
      @mousedown="activate"
    />

    <v-autocomplete
      v-else
      ref="autocompleteRef"
      :model-value="selectedModel"
      v-model:search="searchText"
      :items="candidates"
      :item-title="candidateTitle"
      item-value="product_id"
      return-object
      no-filter
      density="compact"
      variant="outlined"
      hide-details
      clearable
      :disabled="disabled"
      :loading="matching"
      :menu-props="{ maxWidth: 520, maxHeight: 420 }"
      placeholder="Начните вводить наименование..."
      class="flex-grow-1"
      style="min-width:200px"
      @update:search="onSearch"
      @update:model-value="onSelect"
    >
      <template #selection="{ item: it }">
        <span style="white-space:normal;word-break:break-word;line-height:1.3;font-size:12px">
          {{ it?.raw?.name ?? itemName }}
        </span>
      </template>
      <template #item="{ item: it, props: ip }">
        <v-list-item v-bind="ip" :title="undefined">
          <template #prepend>
            <v-avatar size="32" rounded="sm" style="overflow:hidden">
              <img v-if="it.raw.photo_url" :src="it.raw.photo_url"
                style="width:32px;height:32px;object-fit:cover;display:block"
                @error="($event.target as HTMLImageElement).style.display='none'" />
              <v-icon v-else icon="mdi-package-variant" color="grey" size="18" />
            </v-avatar>
          </template>
          <template #title>
            <span style="white-space:normal;word-break:break-word;line-height:1.3">{{ it.raw.name }}</span>
          </template>
          <template #subtitle>
            <span v-if="it.raw.item_type" class="text-caption">{{ it.raw.item_type }}</span>
            <span v-if="it.raw.price != null" class="text-caption ml-2">
              {{ Number(it.raw.price).toLocaleString('ru-RU') }} ₽
            </span>
          </template>
          <template #append>
            <v-chip :color="scoreColor(it.raw.score)" size="x-small" variant="tonal">
              {{ Math.round((it.raw.score ?? 0) * 100) }}%
            </v-chip>
          </template>
        </v-list-item>
      </template>
      <template #no-data>
        <v-list-item>
          <div class="text-caption text-medium-emphasis py-1">
            {{ matching ? 'Поиск…' : (searchText && searchText.length >= 2 ? 'Совпадений нет' : 'Введите минимум 2 символа') }}
          </div>
        </v-list-item>
      </template>
      <template #prepend-item>
        <v-list-item v-if="candidates.length > 5" disabled>
          <div class="text-caption text-medium-emphasis">
            Найдено {{ candidates.length }} — прокрутите список
          </div>
        </v-list-item>
      </template>
      <template #append-item>
        <v-divider />
        <v-list-item link @click="emitCreateNew">
          <template #prepend>
            <v-icon icon="mdi-plus" color="teal" />
          </template>
          <v-list-item-title class="text-teal">Создать новый товар…</v-list-item-title>
        </v-list-item>
      </template>
    </v-autocomplete>
  </div>
</template>

<script setup lang="ts">
// InlineProductMatch — per-row inline catalog matching dropdown (BUG #5).
// Replaces the click-to-open dialog name cell. Queries /products/match as the
// user types (debounced), shows ranked candidates with a status badge, and
// emits a `pick` event with the chosen candidate (or `create-new` to fall back
// to the full product dialog). The parent applies the mutation via
// useItemMatching.applyCandidate so list state is single-sourced.
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import { useItemMatching, type MatchCandidate, type MatchStatus } from '@/composables/useItemMatching'

const props = withDefaults(defineProps<{
  /** Current row name (used as initial query / display fallback). */
  itemName?: string
  /** Whether the row is already bound to a catalog product. */
  productId?: number | null
  /** Match confirmation flag for the row (false = fuzzy, needs confirm). */
  matchConfirmed?: boolean
  disabled?: boolean
  /** Debounce for re-querying matches while typing (ms). */
  debounce?: number
}>(), {
  itemName: '',
  productId: null,
  matchConfirmed: undefined,
  disabled: false,
  debounce: 300,
})

const emit = defineEmits<{
  /** User chose a catalog candidate. Parent applies it to the row. */
  pick: [candidate: MatchCandidate]
  /** User chose "create new" — parent opens the full product dialog. */
  'create-new': []
  /** User cleared the binding. */
  clear: []
}>()

const { matching, matchOne } = useItemMatching()

const candidates = ref<MatchCandidate[]>([])
const status = ref<MatchStatus>('create')
const searchText = ref(props.itemName || '')

// Perf (lazy matcher): the heavy v-autocomplete only mounts when `active` is true.
// Until the user focuses/clicks the row, a lightweight read-only text field is
// shown instead. Once activated for a row it stays active for the session — that
// is intentional and keeps the logic simple while avoiding N mounted autocompletes.
const active = ref(false)
const autocompleteRef = ref<{ focus?: () => void } | null>(null)

// Read-only display text for the lightweight (inactive) state. For both bound
// (productId != null) and unbound rows the visible label is the row's item_name.
const displayName = computed(() => props.itemName || searchText.value || '')

function activate() {
  if (props.disabled || active.value) return
  active.value = true
  // Seed candidates for an already-named row so the menu is useful immediately.
  if ((searchText.value || '').trim().length >= 2) {
    void runMatch(searchText.value)
  }
  // Focus the real autocomplete once it has mounted.
  void nextTick(() => {
    autocompleteRef.value?.focus?.()
  })
}

// Keep the field showing the current name when the row name changes externally.
watch(() => props.itemName, (v) => {
  if ((v || '') !== (searchText.value || '')) searchText.value = v || ''
})

// Display the current binding as a synthetic selection (so the field is not empty).
const selectedModel = computed<MatchCandidate | null>(() => {
  if (props.productId != null) {
    const found = candidates.value.find(c => c.product_id === props.productId)
    if (found) return found
    return {
      product_id: props.productId,
      name: props.itemName || '',
      price: null,
      score: 1,
    }
  }
  return null
})

function candidateTitle(c: MatchCandidate | null): string {
  return c?.name ?? ''
}

// ── Status badge ──────────────────────────────────────────────────────────────
const statusColor = computed(() => {
  if (props.productId != null) {
    return props.matchConfirmed === false ? 'amber' : 'success'
  }
  if (status.value === 'auto') return 'success'
  if (status.value === 'suggest') return 'amber'
  return 'grey'
})
const statusIcon = computed(() => {
  if (props.productId != null) {
    return props.matchConfirmed === false ? 'mdi-alert' : 'mdi-check-circle'
  }
  if (status.value === 'auto') return 'mdi-check-circle'
  if (status.value === 'suggest') return 'mdi-help-circle'
  return 'mdi-plus-circle-outline'
})
const statusTooltip = computed(() => {
  if (props.productId != null) {
    return props.matchConfirmed === false
      ? 'Похожий товар — подтвердите выбор'
      : 'Привязано к каталогу'
  }
  if (status.value === 'auto') return 'Точное совпадение в каталоге'
  if (status.value === 'suggest') return 'Есть похожие товары — выберите'
  return 'В каталоге нет — можно создать новый'
})

function scoreColor(score: number | undefined): string {
  const s = score ?? 0
  if (s >= 0.9) return 'success'
  if (s >= 0.5) return 'amber'
  return 'grey'
}

// ── Debounced matching ──────────────────────────────────────────────────────
let timer: ReturnType<typeof setTimeout> | null = null

async function runMatch(query: string) {
  const q = (query || '').trim()
  if (q.length < 2) {
    candidates.value = []
    status.value = 'create'
    return
  }
  const res = await matchOne(q, 100, true)
  if (res) {
    candidates.value = res.candidates ?? []
    status.value = res.status ?? 'create'
  } else {
    candidates.value = []
    status.value = 'create'
  }
}

function onSearch(text: string) {
  searchText.value = text
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => runMatch(text), props.debounce)
}

function onSelect(val: MatchCandidate | null) {
  if (!val) {
    emit('clear')
    return
  }
  emit('pick', val)
}

function emitCreateNew() {
  emit('create-new')
}

onBeforeUnmount(() => { if (timer) clearTimeout(timer) })
</script>
