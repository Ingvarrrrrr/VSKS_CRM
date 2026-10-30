// Vue directive: v-number-only
// Блокирует ввод недопустимых символов в числовых полях «Кол-во»/«Цена ед.»
// (ItemsTableFlat/ItemsTableStages/ItemsCardsView/ItemsTableWish, владелец
// 29.10.2026): браузерный <input type="number"> САМ пропускает e/E/+/- и не
// проверяет вставку (paste) — v-model.number на таком вводе тихо превращался
// в NaN. Директива вешается на обёртку Vuetify-компонента (<v-text-field>),
// ищет настоящий <input> внутри (el.querySelector) и работает на DOM-уровне,
// независимо от Vuetify-версии/внутренней разметки.
//
// Чистая логика «что допустимо» — ЕДИНСТВЕННЫЙ источник в utils/numberInput.ts
// (sanitizeNumberInput/isAllowedNumberChar, ПРАВИЛО №6) — директива сама
// никаких регулярок не содержит, только слушатели событий.
import type { Directive } from 'vue'
import { sanitizeNumberInput, isAllowedNumberChar } from '@/utils/numberInput'

const ATTACHED_FLAG = '__numberOnlyAttached'

function findInput(el: HTMLElement): HTMLInputElement | null {
  if (el instanceof HTMLInputElement) return el
  return el.querySelector('input')
}

function attach(el: HTMLElement) {
  const input = findInput(el)
  if (!input || (input as any)[ATTACHED_FLAG]) return
  ;(input as any)[ATTACHED_FLAG] = true

  // beforeinput: ловит и клавиатуру, и IME/автозаполнение — проверяем
  // символ(ы), которые браузер собирается вставить, ДО того как они попали
  // в поле. Не трогаем insertFromPaste/insertFromDrop — за них отвечает
  // отдельный 'paste' listener ниже (там нужна полная пересборка строки,
  // не посимвольная проверка).
  input.addEventListener('beforeinput', (e: InputEvent) => {
    if (e.inputType !== 'insertText' && e.inputType !== 'insertCompositionText') return
    const data = e.data
    if (data == null) return
    for (const ch of data) {
      if (!isAllowedNumberChar(ch)) {
        e.preventDefault()
        return
      }
    }
    // Второй разделитель дробной части — недопустим (нормализация запятой в
    // точку делает оба символа одним и тем же разделителем).
    if ((data === '.' || data === ',') && /[.,]/.test(input.value)) {
      e.preventDefault()
    }
  })

  // keydown: доп. защита для минуса/экспоненты — часть браузеров считает их
  // валидными для type="number" и может обработать раньше beforeinput
  // (стрелки вверх/вниз у type="number" тоже меняют значение шагом ±1,
  // что для минуса эквивалентно обходу запрета — блокируем явные клавиши).
  input.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'e' || e.key === 'E' || e.key === '+' || e.key === '-') {
      e.preventDefault()
    }
  })

  // paste: вставка произвольного текста — вырезаем всё недопустимое и
  // собираем итоговую строку сами (native paste в type="number" либо
  // вставляет текст «как есть» без проверки, либо откатывает его в пустое
  // поле при невалидности — оба варианта не то, что нужно).
  input.addEventListener('paste', (e: ClipboardEvent) => {
    e.preventDefault()
    const text = e.clipboardData?.getData('text') ?? ''
    const start = input.selectionStart ?? input.value.length
    const end = input.selectionEnd ?? input.value.length
    const merged = input.value.slice(0, start) + text + input.value.slice(end)
    const sanitized = sanitizeNumberInput(merged)
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
    if (nativeSetter) nativeSetter.call(input, sanitized)
    else input.value = sanitized
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

export const vNumberOnly: Directive<HTMLElement> = {
  mounted(el) {
    attach(el)
  },
  updated(el) {
    // Vuetify может пересобрать внутренний <input> между рендерами (редко,
    // но дёшево перепроверить) — attach() сам не делает ничего, если на
    // текущем <input> уже стоит флаг.
    attach(el)
  },
}
