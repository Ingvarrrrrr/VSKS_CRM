<template>
  <div class="stacked-region">
    <div class="stacked-region__name">
      {{ region }}
      <small v-if="shtab">{{ shtab }}</small>
    </div>
    <div
      class="stacked-region__track"
      :title="tooltip"
    >
      <div
        class="stacked-region__bar"
        :style="{ width: trackPct + '%' }"
      >
        <div
          v-if="segs.working > 0"
          class="seg seg--working"
          :style="{ flex: segs.working }"
          @click.stop="$emit('segment-click', { region, state: 'working' })"
        >
          <span v-if="workingPct >= 12">{{ segs.working }} раб.</span>
        </div>
        <div
          v-if="segs.repair > 0"
          class="seg seg--repair"
          :style="{ flex: segs.repair }"
          @click.stop="$emit('segment-click', { region, state: 'in_repair' })"
        >
          <span v-if="repairPct >= 12">{{ segs.repair }} рем.</span>
        </div>
        <div
          v-if="segs.broken > 0"
          class="seg seg--broken"
          :style="{ flex: segs.broken }"
          @click.stop="$emit('segment-click', { region, state: 'broken' })"
        >
          <span v-if="brokenPct >= 12">{{ segs.broken }}</span>
        </div>
        <!-- 2026-09 (владелец: «сумма сегментов должна равняться числу справа»):
             машины без заполненного Vehicle.state не попадали НИ В ОДИН сегмент —
             у мест, где нет донецких/курских машин, полоса была почти пустой, хотя
             count справа показывал реальное число (владелец: «Место не указано» 34
             машины — полоса должна быть заполнена целиком). Backend уже кладёт их в
             by_state.unknown (см. vehicles_dashboard.py: r.state or "unknown") —
             фронт просто не читал этот ключ. Нейтральный серый — не путать с in_repair/broken. -->
        <div
          v-if="segs.unspecified > 0"
          class="seg seg--unspecified"
          :style="{ flex: segs.unspecified }"
          @click.stop="$emit('segment-click', { region, state: 'unspecified' })"
        >
          <span v-if="unspecifiedPct >= 12">{{ segs.unspecified }} не указ.</span>
        </div>
      </div>
    </div>
    <div class="stacked-region__count">{{ count }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  region: string
  shtab?: string
  count: number
  maxCount: number
  working: number
  inRepair: number
  broken: number
  needsRepair: number
  destroyed: number
  utilized: number
  // 2026-09: машины с пустым/неизвестным Vehicle.state (см. комментарий у сегмента
  // выше) — раньше молча выпадали из полосы, сумма сегментов не сходилась с count.
  unspecified?: number
}>()

defineEmits<{
  (e: 'segment-click', payload: { region: string; state: string }): void
}>()

const segs = computed(() => ({
  working: props.working,
  repair: props.inRepair + props.needsRepair,
  broken: props.broken + props.destroyed + props.utilized,
  unspecified: props.unspecified || 0,
}))

const trackPct = computed(() =>
  props.maxCount > 0 ? Math.max(6, Math.round((props.count / props.maxCount) * 100)) : 6
)

const total = computed(() => segs.value.working + segs.value.repair + segs.value.broken + segs.value.unspecified || 1)
const workingPct     = computed(() => (segs.value.working     / total.value) * 100)
const repairPct      = computed(() => (segs.value.repair      / total.value) * 100)
const brokenPct      = computed(() => (segs.value.broken      / total.value) * 100)
const unspecifiedPct = computed(() => (segs.value.unspecified / total.value) * 100)

const tooltip = computed(() =>
  `Рабочих: ${segs.value.working}` +
  ` · В ремонте / требует ремонта: ${segs.value.repair}` +
  ` · Не на ходу / списано: ${segs.value.broken}` +
  ` · Состояние не указано: ${segs.value.unspecified}`
)
</script>

<style scoped>
.stacked-region {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 0;
}

.stacked-region__name {
  flex: 0 0 148px;
  font-weight: 600;
  font-size: 13px;
  color: var(--text, #e9edf5);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.stacked-region__name small {
  display: block;
  color: var(--muted, #8a93a8);
  font-weight: 500;
  font-size: 11px;
  margin-top: 1px;
}

.stacked-region__track {
  flex: 1;
  height: 26px;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 8px;
  border: 1px solid var(--line, #222838);
  overflow: hidden;
}

.stacked-region__bar {
  display: flex;
  height: 100%;
  border-radius: 7px;
  overflow: hidden;
  transition: width 0.4s ease;
}

.seg {
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  cursor: pointer;
  transition: filter 0.15s;
  font-size: 11px;
  font-weight: 700;
  color: rgba(10, 13, 20, 0.9);
  white-space: nowrap;
  min-width: 0;
}
.seg:hover { filter: brightness(1.15); }
.seg span { pointer-events: none; overflow: hidden; text-overflow: ellipsis; padding: 0 4px; }

.seg--working {
  background: linear-gradient(90deg, #22c997, #5dd0ff);
}
.seg--repair {
  background: linear-gradient(90deg, #f6b34a, #ff8a4a);
}
.seg--broken {
  background: linear-gradient(90deg, #ff5b6a, #ff3b8b);
}
/* Нейтральный приглушённый серый — сознательно НЕ похож на working/repair/broken,
   чтобы «состояние не указано» не читалось как ещё одна оценка состояния парка. */
.seg--unspecified {
  background: repeating-linear-gradient(
    135deg,
    rgba(148, 163, 184, 0.55) 0px, rgba(148, 163, 184, 0.55) 6px,
    rgba(148, 163, 184, 0.35) 6px, rgba(148, 163, 184, 0.35) 12px
  );
  color: rgba(15, 18, 26, 0.85);
}

.stacked-region__count {
  flex: 0 0 36px;
  text-align: right;
  font-weight: 700;
  font-size: 13px;
  color: var(--text, #e9edf5);
}

/* Light theme */
.v-theme--light .stacked-region__name { color: #1a1d23; }
.v-theme--light .stacked-region__count { color: #1a1d23; }
.v-theme--light .stacked-region__name small { color: #6b7280; }
.v-theme--light .stacked-region__track {
  background: rgba(0, 0, 0, 0.04);
  border-color: #e2e6f0;
}
.v-theme--light .seg { color: #fff; }
</style>
