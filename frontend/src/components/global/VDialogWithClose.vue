<script setup lang="ts">
// Обёртка над штатным Vuetify VDialog, добавляющая крестик закрытия в правый
// верхний угол — универсально, без правки 155 отдельных диалогов (см.
// ПРАВИЛО №6: один способ закрытия диалога, а не 155 копий).
//
// ПОЧЕМУ обёртка компонентом, а не MutationObserver (как было в первой
// версии этого решения): чтобы узнать persistent, первая версия читала
// `el.__vueParentComponent.props.persistent` — внутреннее поле, которое Vue 3
// проставляет на DOM-узел только при `__DEV__ || __VUE_PROD_DEVTOOLS__`
// (см. node_modules/@vue/runtime-core/dist/runtime-core.esm-bundler.js,
// строки с `def(el, "__vueParentComponent", ...)`). В проде Vite по
// умолчанию __VUE_PROD_DEVTOOLS__=false, значит `__vueParentComponent`
// отсутствует — проверено вживую на реальной prod-сборке в контейнере
// frontend_a: `el.__vueParentComponent` был `undefined` на открытом диалоге.
// Это значит, что MutationObserver-версия НЕ отличала persistent от обычного
// диалога в проде и рисовала бы нерабочий крестик на диалогах подтверждения/
// несохранённых изменений (Vuetify игнорирует Esc/клик-вне для persistent —
// крестик выглядел бы, но не закрывал).
//
// Эта версия получает `persistent` как обычный реактивный prop компонента —
// никаких внутренних API Vue, работает одинаково в dev и в проде. Закрытие —
// через `update:modelValue` (тот же канал, что и v-model самого диалога),
// что надёжнее операции "сгенерировать Esc" (не зависит от фокуса/scrim).
//
// Крестик НЕ показываем, если в контенте уже есть своя кнопка закрытия
// (иконка .mdi-close или элемент с aria-label/title "Закрыть"/"Close") —
// определяем DOM-проверкой после рендера слота (сам DOM-осмотр не зависит от
// __vueParentComponent и одинаково работает в dev/prod — это подтвердилось на
// диалогах «Добавить контрагента» и «Добавить субсидию», у которых уже есть
// своя кнопка, и наш крестик там не задваивался).
import { computed, nextTick, ref, watch, useAttrs, useSlots } from 'vue'
import { VDialog } from 'vuetify/components/VDialog'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  modelValue?: boolean
  persistent?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const attrs = useAttrs()
const slots = useSlots()

const wrapRef = ref<HTMLElement | null>(null)
// null = ещё не проверяли (крестик скрыт, чтобы не мигнуть дублем)
const hasOwnClose = ref<boolean | null>(null)

function checkOwnClose() {
  const el = wrapRef.value
  if (!el) return
  const candidates = Array.from(el.querySelectorAll('.mdi-close, [aria-label], [title]')) as HTMLElement[]
  hasOwnClose.value = candidates.some((node) => {
    if (node.classList.contains('hv-dialog-close-btn') || node.closest('.hv-dialog-close-btn')) {
      return false
    }
    if (node.classList.contains('mdi-close')) return true
    const label = `${node.getAttribute('aria-label') || ''} ${node.getAttribute('title') || ''}`.toLowerCase()
    return label.includes('закрыть') || label.includes('close')
  })
}

watch(
  () => props.modelValue,
  async (isOpen) => {
    if (!isOpen) return
    hasOwnClose.value = null
    // ждём, пока слот полностью домонтируется (в т.ч. вложенные async-компоненты)
    await nextTick()
    await nextTick()
    checkOwnClose()
  },
  { immediate: true },
)

const showCloseBtn = computed(() => !props.persistent && hasOwnClose.value === false)

function close() {
  emit('update:modelValue', false)
}

function onUpdateModelValue(value: boolean) {
  emit('update:modelValue', value)
}
</script>

<template>
  <VDialog
    v-bind="attrs"
    :model-value="props.modelValue"
    :persistent="props.persistent"
    @update:model-value="onUpdateModelValue"
  >
    <template v-if="slots.activator" #activator="activatorSlotProps">
      <slot name="activator" v-bind="activatorSlotProps" />
    </template>
    <template #default="defaultSlotProps">
      <div ref="wrapRef" class="hv-dialog-wrap">
        <slot name="default" v-bind="defaultSlotProps" />
        <button
          v-if="showCloseBtn"
          type="button"
          class="hv-dialog-close-btn"
          aria-label="Закрыть"
          title="Закрыть"
          @click.stop="close"
        >
          <span class="mdi mdi-close" aria-hidden="true"></span>
        </button>
      </div>
    </template>
    <template v-for="name in Object.keys(slots).filter((n) => n !== 'activator' && n !== 'default')" #[name]="slotProps" :key="name">
      <slot :name="name" v-bind="slotProps ?? {}" />
    </template>
  </VDialog>
</template>

<style>
.hv-dialog-wrap {
  position: relative;
}
.hv-dialog-close-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 20;
  width: 32px;
  height: 32px;
  min-width: 32px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.7);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
  transition: background-color 0.15s ease;
}
.hv-dialog-close-btn:hover {
  background-color: rgba(var(--v-theme-on-surface), 0.08);
}
.hv-dialog-close-btn:focus-visible {
  outline: 2px solid rgba(var(--v-theme-primary), 0.6);
  outline-offset: 1px;
}
</style>
