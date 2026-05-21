<template>
  <div class="stage-stepper" :class="{ 'stage-stepper--overdue': isOverdue }">
    <div class="stage-stepper__track">
      <template v-for="(step, i) in steps" :key="step.key">
        <div
          class="step"
          :class="{
            'step--done':    stepState(i) === 'done',
            'step--active':  stepState(i) === 'active',
            'step--pending': stepState(i) === 'pending',
            'step--overdue': isOverdue,
          }"
        >
          <div class="step__dot">
            <span v-if="isOverdue">!</span>
            <span v-else-if="stepState(i) === 'done'">✓</span>
            <span v-else>{{ i + 1 }}</span>
          </div>
          <div class="step__label">{{ step.label }}</div>
        </div>
        <div
          v-if="i < steps.length - 1"
          class="connector"
          :class="{
            'connector--done':   connectorDone(i),
            'connector--overdue': isOverdue,
          }"
        />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type Stage =
  | 'created'
  | 'tech_inspect'
  | 'med_inspect'
  | 'in_progress'
  | 'closing'
  | 'on_review'
  | 'closed'
  | 'overdue'

const props = defineProps<{
  currentStage: Stage
}>()

const steps = [
  { key: 'created',      label: 'Создан' },
  { key: 'tech_inspect', label: 'Тех.осмотр' },
  { key: 'med_inspect',  label: 'Медосмотр' },
  { key: 'in_progress',  label: 'В пути' },
  { key: 'closing',      label: 'Закрытие' },
  { key: 'on_review',    label: 'На проверке' },
  { key: 'closed',       label: 'Закрыт' },
]

const isOverdue = computed(() => props.currentStage === 'overdue')

const activeIndex = computed(() => {
  if (isOverdue.value) return -1
  return steps.findIndex(s => s.key === props.currentStage)
})

function stepState(i: number): 'done' | 'active' | 'pending' {
  if (isOverdue.value) return 'pending'
  if (i < activeIndex.value) return 'done'
  if (i === activeIndex.value) return 'active'
  return 'pending'
}

function connectorDone(i: number): boolean {
  if (isOverdue.value) return false
  return i < activeIndex.value
}
</script>

<style scoped>
.stage-stepper {
  padding: 10px 4px;
}

.stage-stepper__track {
  display: flex;
  align-items: flex-start;
  gap: 0;
}

.step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.step__dot {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.06);
  border: 1.5px solid var(--muted, #8a93a8);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 800;
  color: var(--muted, #8a93a8);
  transition: background 0.2s, border-color 0.2s, box-shadow 0.2s;
}

.step__label {
  font-size: 10.5px;
  color: var(--muted, #8a93a8);
  font-weight: 600;
  white-space: nowrap;
  text-align: center;
}

/* done */
.step--done .step__dot {
  background: var(--ok, #22c997);
  border-color: var(--ok, #22c997);
  color: #0a0d14;
}
.step--done .step__label {
  color: #a8efd2;
}

/* active */
.step--active .step__dot {
  background: var(--accent, #6aa6ff);
  border-color: var(--accent, #6aa6ff);
  color: #0a0d14;
  box-shadow: 0 0 0 4px rgba(106, 166, 255, 0.18);
}
.step--active .step__label {
  color: #cfe1ff;
  font-weight: 700;
}

/* overdue — all red */
.stage-stepper--overdue .step__dot {
  background: rgba(255, 91, 106, 0.15);
  border-color: var(--alert, #ff5b6a);
  color: var(--alert, #ff5b6a);
}
.stage-stepper--overdue .step__label {
  color: var(--alert, #ff5b6a);
}

/* connector */
.connector {
  flex: 1;
  min-width: 16px;
  height: 2px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 1px;
  margin-top: 10px; /* vertically align with dot center */
  transition: background 0.2s;
}

.connector--done {
  background: var(--ok, #22c997);
}

.stage-stepper--overdue .connector {
  background: rgba(255, 91, 106, 0.35);
}
</style>
