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
// Крестик НЕ показываем, если в контенте уже есть своя кнопка закрытия:
// элемент с aria-label/title "Закрыть"/"Close", либо .mdi-close внутри
// заголовка/тулбара (.v-card-title, .v-card-item, .v-toolbar) — определяем
// DOM-проверкой после рендера слота (сам DOM-осмотр не зависит от
// __vueParentComponent и одинаково работает в dev/prod — это подтвердилось на
// диалогах «Добавить контрагента» и «Добавить субсидию», у которых уже есть
// своя кнопка, и наш крестик там не задваивался). Любую .mdi-close в теле
// диалога (например кнопку «Отклонить») своей НЕ считаем — иначе ложное
// срабатывание; крестик в v-chip (closable-чип) тоже не считается.
// Показываем крестик ВСЕГДА, включая persistent-диалоги — см. showCloseBtn.
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

const closeBtnRef = ref<HTMLElement | null>(null)
// null = ещё не проверяли (крестик скрыт, чтобы не мигнуть дублем)
const hasOwnClose = ref<boolean | null>(null)

function checkOwnClose() {
  const btn = closeBtnRef.value
  // контейнер = .v-overlay__content (родитель нашей кнопки), а не div-обёртка —
  // обёртку убрали, чтобы не ломать CSS-селекторы Vuetify вида
  // `.v-dialog > .v-overlay__content > .v-card`, завязанные на прямое соседство.
  const container = btn?.parentElement
  if (!container) return
  const labelCandidates = Array.from(container.querySelectorAll('[aria-label], [title]')) as HTMLElement[]
  const hasLabelClose = labelCandidates.some((node) => {
    if (node === btn || node.closest('.hv-dialog-close-btn')) return false
    const label = `${node.getAttribute('aria-label') || ''} ${node.getAttribute('title') || ''}`.toLowerCase()
    return label.includes('закрыть') || label.includes('close')
  })
  // .mdi-close считаем «своей кнопкой закрытия» только в заголовке/тулбаре —
  // иначе ложно срабатывает на любую иконку в теле (например «Отклонить» с
  // prepend-icon mdi-close). Иконка внутри v-chip (closable-чип) не считается.
  const iconCandidates = Array.from(
    container.querySelectorAll('.v-card-title .mdi-close, .v-card-item .mdi-close, .v-toolbar .mdi-close'),
  ) as HTMLElement[]
  const hasIconClose = iconCandidates.some((node) => {
    if (node.closest('.hv-dialog-close-btn')) return false
    if (node.closest('.v-chip')) return false
    return true
  })
  hasOwnClose.value = hasLabelClose || hasIconClose
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

// Показываем всегда, включая persistent: крестик — явное действие
// пользователя, а persistent блокирует только неявные способы закрытия
// (клик вне диалога и Esc), не явный клик по кнопке.
const showCloseBtn = computed(() => hasOwnClose.value === false)

// isActive из слота Vuetify — закрывает и «неуправляемые» диалоги (только activator,
// без v-model), у которых emit update:modelValue никто не слушает.
function close(slotProps?: { isActive?: { value: boolean } }) {
  emit('update:modelValue', false)
  if (slotProps?.isActive) slotProps.isActive.value = false
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
      <slot name="default" v-bind="defaultSlotProps" />
      <button
        ref="closeBtnRef"
        v-show="showCloseBtn"
        type="button"
        class="hv-dialog-close-btn"
        aria-label="Закрыть"
        title="Закрыть"
        @click.stop="close(defaultSlotProps)"
      >
        <span class="mdi mdi-close" aria-hidden="true"></span>
      </button>
    </template>
    <template v-for="name in Object.keys(slots).filter((n) => n !== 'activator' && n !== 'default')" #[name]="slotProps" :key="name">
      <slot :name="name" v-bind="slotProps ?? {}" />
    </template>
  </VDialog>
</template>

<style>
/* Кнопка абсолютно спозиционирована относительно .v-overlay__content
   (её родитель в DOM — см. checkOwnClose), у него position:absolute от
   Vuetify, поэтому явный position:relative на обёртке больше не нужен —
   обёртку убрали, чтобы не ломать `.v-dialog > .v-overlay__content > .v-card`. */
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
/* Крестик не должен налезать на кнопки в правом верхнем углу заголовка.
   v-show ставит style="display: none;" на скрытую кнопку — селектор ловит
   только видимую. */
.v-overlay__content:has(> .hv-dialog-close-btn:not([style*="display: none"])) > .v-card > .v-card-title,
.v-overlay__content:has(> .hv-dialog-close-btn:not([style*="display: none"])) > .v-card > .v-card-item,
.v-overlay__content:has(> .hv-dialog-close-btn:not([style*="display: none"])) > .v-card > .v-toolbar,
.v-overlay__content:has(> .hv-dialog-close-btn:not([style*="display: none"])) > form > .v-card > .v-card-title,
.v-overlay__content:has(> .hv-dialog-close-btn:not([style*="display: none"])) > form > .v-card > .v-card-item,
.v-overlay__content:has(> .hv-dialog-close-btn:not([style*="display: none"])) > form > .v-card > .v-toolbar {
  padding-right: 48px !important;
}
</style>
