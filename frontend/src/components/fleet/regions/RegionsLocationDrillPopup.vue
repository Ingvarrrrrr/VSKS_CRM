<template>
  <!-- 2026-09: раньше попап показывал организацию (по названию), к которой якобы
       привязан пин; теперь пин/карточка = место нахождения, попап показывает
       реальный список машин в этом месте (GET /vehicles-dashboard/drill?dimension=region). -->
  <teleport to="body">
    <transition name="rv-popup-fade">
      <div v-if="selectedLocation" class="rv-popup-overlay" @click.self="$emit('close')">
        <div class="rv-popup" :class="{ 'rv-popup--light': !isDark }">
          <div class="rv-popup__head">
            <div class="rv-popup__abbr" :style="{ background: '#6aa6ff' }">{{ locationAbbr(selectedLocation) }}</div>
            <div>
              <div class="rv-popup__nm">{{ selectedLocation }}</div>
              <div v-if="selectedLocation && locationSubtitle(selectedLocation)" class="rv-popup__sub">{{ locationSubtitle(selectedLocation) }}</div>
            </div>
            <button class="rv-popup__close" @click="$emit('close')">✕</button>
          </div>
          <div class="rv-popup__body">
            <div class="rv-popup__stat">
              <span class="rv-popup__stat-l">ТС всего</span>
              <span class="rv-popup__stat-v">{{ selectedLocationItem?.count ?? 0 }}</span>
            </div>
            <div v-if="drillLoading" class="rv-loading" style="min-height:60px">
              <div class="rv-spinner"></div>
            </div>
            <template v-else>
              <!-- 2026-09 (владелец: «в попапе нужен поиск, иначе трудно найти
                   машину») — фильтр по гос.№/марке/модели прямо по загруженному
                   списку (он уже маленький — конкретное место нахождения). -->
              <div v-if="drillVehicles.length" class="rv-popup__filter">
                <span class="rv-popup__filter-ic">⌕</span>
                <input
                  :value="drillFilterQuery"
                  type="text"
                  class="rv-popup__filter-input"
                  placeholder="Фильтр: гос.№, марка, модель…"
                  @input="$emit('update:drillFilterQuery', ($event.target as HTMLInputElement).value)"
                />
                <button
                  v-if="drillFilterQuery"
                  class="rv-popup__filter-clear"
                  title="Очистить"
                  @click="$emit('update:drillFilterQuery', '')"
                >✕</button>
              </div>
              <div v-if="drillVehicles.length" class="rv-popup__filter-count">
                {{ filteredDrillVehicles.length }} из {{ drillVehicles.length }}
              </div>
              <div class="rv-popup__vehicles">
                <div
                  v-for="v in filteredDrillVehicles"
                  :key="v.vehicle_id"
                  class="rv-popup__veh"
                  @click="$emit('go-to-vehicle', v.vehicle_id)"
                >
                  <!-- 2026-09: иконка по «Кузову» — единое правило (см. VehicleCard.vue) -->
                  <VehicleTypeIcon :body-type="v.body_type" :size="22" class="rv-popup__veh-ic" />
                  <LicensePlate :modelValue="v.plate" size="sm" />
                  <span class="rv-popup__veh-nm">{{ v.brand_model || '—' }}</span>
                </div>
                <div v-if="!drillVehicles.length" class="rv-empty">Нет машин</div>
                <div v-else-if="!filteredDrillVehicles.length" class="rv-empty">
                  Нет машин по запросу «{{ drillFilterQuery.trim() }}»
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup lang="ts">
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import VehicleTypeIcon from '@/components/vehicles/VehicleTypeIcon.vue'
import type { RegionItem } from '@/composables/fleet/regions/useRegionsData'
import { useLocationDisplay } from '@/composables/fleet/regions/useLocationDisplay'

defineProps<{
  isDark: boolean
  selectedLocation: string | null
  selectedLocationItem: RegionItem | null
  drillLoading: boolean
  drillVehicles: any[]
  filteredDrillVehicles: any[]
  drillFilterQuery: string
}>()

defineEmits<{
  (e: 'close'): void
  (e: 'go-to-vehicle', vehicleId: number): void
  (e: 'update:drillFilterQuery', value: string): void
}>()

const { locationAbbr, locationSubtitle } = useLocationDisplay()
</script>

<!-- 2026-09: попап телепортируется в <body> — реально живёт ВНЕ DOM-поддерева
     .regions-view, поэтому классы .rv-popup*/.rv-popup-fade-* держим здесь, в
     собственном scoped-style компонента (Vue-скоуп работает через
     data-атрибут на самих элементах, а не через положение в DOM — teleport
     ему не мешает, в отличие от глобального CSS с префиксом `.regions-view`,
     который бы сюда физически не дотянулся). .rv-loading/.rv-spinner/.rv-empty
     используются и здесь, и в обычных (нетелепортируемых) компонентах —
     поэтому они не дублируются тут, а определены один раз без префикса в
     styles/fleet-regions.css. -->
<style scoped>
.rv-popup-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.45);
  z-index: 9998;
  display: flex;
  align-items: center;
  justify-content: center;
}

.rv-popup {
  background: #141823;
  border: 1px solid #2b3245;
  border-radius: 18px;
  padding: 22px;
  min-width: 300px;
  max-width: 380px;
  width: 90%;
  z-index: 9999;
  box-shadow: 0 20px 60px rgba(0,0,0,.5);
  /* 2026-09 (правка владельца, «10 машин без прокрутки»): попап растёт вместе
     со списком (см. .rv-popup__vehicles ниже), но не дальше 90% высоты
     окна — иначе на ноутбучном/мобильном экране он вылезал бы за край.
     display:flex + overflow:hidden здесь и min-height:0 на детях — стандартный
     паттерн «шапка фиксирована, скроллится только внутренний список»: сам
     .rv-popup не скроллится, скроллится только .rv-popup__vehicles. */
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.rv-popup--light { background: #fff; border-color: #e2e6f0; }

.rv-popup__head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-shrink: 0;
}

.rv-popup__abbr {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 13px;
  color: #0a0d14;
  flex-shrink: 0;
}

.rv-popup__nm { font-weight: 800; font-size: 17px; }
.rv-popup__sub { color: var(--rv-muted); font-size: 12px; margin-top: 2px; }

.rv-popup__close {
  margin-left: auto;
  background: none;
  border: none;
  color: var(--rv-muted);
  cursor: pointer;
  font-size: 16px;
  padding: 4px;
  border-radius: 6px;
  transition: color 0.12s;
}
.rv-popup__close:hover { color: var(--rv-text); }

.rv-popup__body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  /* flex:1 + min-height:0 — тело растёт до max-height родителя, отдавая
     освободившееся место списку машин, но не выталкивает попап за экран
     (min-height:0 обязателен — без него flex-элемент не хочет сжиматься
     ниже контента, и внутренний скролл .rv-popup__vehicles не срабатывает). */
  flex: 1 1 auto;
  min-height: 0;
}

.rv-popup__stat {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-radius: 10px;
  background: rgba(255,255,255,.03);
  border: 1px solid var(--rv-line);
  flex-shrink: 0;
}
.rv-popup--light .rv-popup__stat { background: #f4f6fb; border-color: #e2e6f0; }

.rv-popup__stat-l { color: var(--rv-muted); font-size: 12px; }
.rv-popup__stat-v { font-weight: 700; font-size: 13px; }

/* 2026-09 (владелец: «в попапе нужен поиск») — фильтр по уже загруженному
   списку машин конкретного места (список маленький, серверный запрос не нужен). */
.rv-popup__filter {
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(255,255,255,.03);
  border: 1px solid var(--rv-line);
  border-radius: 10px;
  padding: 7px 10px;
  margin-bottom: 8px;
  flex-shrink: 0;
}
.rv-popup--light .rv-popup__filter { background: #f4f6fb; border-color: #e2e6f0; }
.rv-popup__filter-ic { color: var(--rv-muted); font-size: 13px; flex-shrink: 0; }
.rv-popup__filter-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--rv-text);
  font-size: 12.5px;
  font-family: inherit;
}
.rv-popup__filter-input::placeholder { color: var(--rv-muted2); }
.rv-popup__filter-clear {
  border: none;
  background: none;
  color: var(--rv-muted);
  cursor: pointer;
  font-size: 11px;
  flex-shrink: 0;
}
.rv-popup__filter-clear:hover { color: var(--rv-text); }
.rv-popup__filter-count {
  color: var(--rv-muted);
  font-size: 11.5px;
  margin: -2px 0 8px 2px;
  flex-shrink: 0;
}

.rv-popup__vehicles {
  display: grid;
  align-content: start;
  gap: 6px;
  /* 2026-09 (правка владельца, «10 машин без прокрутки»): было фиксированных
     260px (~5 строк) — вдвое мало. flex:1 (родитель .rv-popup__body — flex-
     column) отдаёт этому блоку всё место, оставшееся внутри .rv-popup
     max-height:90vh после шапки и строки «ТС всего»; на типичном
     ноутбучном/десктопном окне это ~550-650px (≈10-13 строк по ~44px),
     на мобильном 90vh даёт пропорционально меньше, но всё равно больше
     исходных 260px. min-height задаёт лишь запасной вариант на случай,
     если flex-родитель почему-то не растянулся (не должно случаться) —
     без него список выглядел бы куце даже при малом числе машин. Скролл
     остаётся для случаев, когда список не помещается целиком.
     Watch out: min-height:0 обязателен вместе с flex:1 — иначе flex-item
     не сжимается ниже своего контента и overflow-y:auto не срабатывает. */
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
}
.rv-popup__veh {
  display: grid;
  grid-template-columns: auto auto 1fr;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(255,255,255,.03);
  border: 1px solid var(--rv-line);
  cursor: pointer;
  font-size: 12.5px;
  transition: border-color 0.12s;
}
.rv-popup__veh:hover { border-color: var(--rv-accent); }
.rv-popup--light .rv-popup__veh { background: #f4f6fb; }
.rv-popup__veh-ic { flex-shrink: 0; opacity: 0.9; }
.rv-popup__veh-nm {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rv-popup__footer { display: flex; justify-content: flex-end; }

/* ── Popup transition ───────────────────────────────────────────────────── */
.rv-popup-fade-enter-active,
.rv-popup-fade-leave-active { transition: opacity 0.18s ease; }
.rv-popup-fade-enter-from,
.rv-popup-fade-leave-to { opacity: 0; }
</style>
