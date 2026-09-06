// «Летящая стрелка с пунктирным следом» — универсальный визуальный гид к полю
// формы (используется публикацией, позициями, субсидией и т.д. по всей
// CreateOrderView.vue). Вынесено без изменения поведения.
//
// onBeforeNavigate — вызывается перед наведением на цель ВНЕ диалога публикации
// (тот же список IN_DIALOG_TARGETS, что и раньше) — раньше это было прямое
// `publishDialog.value = false; pendingPlatform.value = null` внутри
// guideArrowTo; теперь колбэк передаётся снаружи, чтобы стрелка не завязывалась
// на детали диалога публикации (единственный вызывающий её сейчас компонент).
import { ref, nextTick } from 'vue'

export function useGuideArrow(onBeforeNavigate?: (target: string) => void) {
  const guideArrowVisible = ref(false)
  const guideArrowPos = ref({ x: 0, y: 0 })
  const guideArrowAngle = ref(0)
  const guideArrowArrived = ref(false)
  const guideTrail = ref<{ x: number; y: number }[]>([])

  // pointer / glow state
  const pointerTarget = ref<string | null>(null)
  const okpd2Pointer = ref(false)
  const auctionPointerTarget = ref<string | null>(null)
  let _pointerTimer: ReturnType<typeof setTimeout> | null = null
  let _okpd2Timer: ReturnType<typeof setTimeout> | null = null
  let _auctionPointerTimer: ReturnType<typeof setTimeout> | null = null

  const AUCTION_TARGETS = new Set(['auction-date', 'auction-bet'])

  let _guideRafId: number | null = null
  let _guideSafetyTimer: ReturnType<typeof setTimeout> | null = null

  function _getDestCenter(el: HTMLElement): { x: number; y: number } {
    const r = el.getBoundingClientRect()
    return { x: r.left + r.width / 2, y: r.top - 30 }
  }

  function clearGuideArrow() {
    guideArrowVisible.value = false
    guideArrowArrived.value = false
    guideTrail.value = []
    if (_guideRafId !== null) { cancelAnimationFrame(_guideRafId); _guideRafId = null }
    if (_guideSafetyTimer !== null) { clearTimeout(_guideSafetyTimer); _guideSafetyTimer = null }
  }

  async function guideArrowTo(target: string) {
    // Отменить предыдущий
    clearGuideArrow()

    const IN_DIALOG_TARGETS = new Set(['auction-date', 'auction-bet', 'okpd2'])
    // Наведение на КОНКРЕТНУЮ строку позиций: target вида 'item:<uid>'. id='item-row-<uid>'
    // уже проставлен на карточку/строку во всех трёх видах (ItemsCardsView/ItemsTableFlat/
    // ItemsTableStages, см. эти файлы) — тот же приём, что highlightMissingCategoryForPlan
    // в PurchaseItemsEditor.vue. Работает и на мобильных карточках, и в десктоп-таблице.
    const itemUid = target.startsWith('item:') ? target.slice(5) : null

    // Для out-of-dialog полей: закрыть диалог сначала
    if (!IN_DIALOG_TARGETS.has(target)) {
      onBeforeNavigate?.(target)
    }

    await nextTick()

    const el = itemUid != null
      ? document.getElementById('item-row-' + itemUid)
      : document.getElementById('pub-target-' + target)
    if (!el) return

    // Старт: правый верхний угол вьюпорта (где снэкбар)
    const startX = window.innerWidth - 100
    const startY = 90
    guideArrowPos.value = { x: startX, y: startY }
    guideTrail.value = [{ x: startX, y: startY }]
    guideArrowVisible.value = true
    guideArrowArrived.value = false

    // Инициировать плавный скролл к полю
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })

    // Также выставить glow
    if (itemUid != null) {
      // Строка позиций не обёрнута pub-glow div'ом (живёт в дочернем компоненте) —
      // подсвечиваем напрямую тем же глобальным pulse-классом, что и
      // highlightMissingCategoryForPlan в PurchaseItemsEditor.vue (.plan-bulk-row-pulse,
      // стиль объявлен там же, global, не scoped).
      el.classList.add('plan-bulk-row-pulse')
      setTimeout(() => el.classList.remove('plan-bulk-row-pulse'), 3000)
    } else if (AUCTION_TARGETS.has(target)) {
      if (_auctionPointerTimer) clearTimeout(_auctionPointerTimer)
      auctionPointerTarget.value = target
    } else if (target === 'okpd2') {
      if (_okpd2Timer) clearTimeout(_okpd2Timer)
      okpd2Pointer.value = true
    } else {
      if (_pointerTimer) clearTimeout(_pointerTimer)
      pointerTarget.value = target
    }

    const LERP = 0.07
    const ARRIVE_DIST = 12
    const TRAIL_MIN_DIST = 6
    let arrived = false

    function tick() {
      const dest = _getDestCenter(el!)
      const cx = guideArrowPos.value.x
      const cy = guideArrowPos.value.y

      if (!arrived) {
        const dx = dest.x - cx
        const dy = dest.y - cy
        const dist = Math.sqrt(dx * dx + dy * dy)
        guideArrowAngle.value = (Math.atan2(dy, dx) * 180) / Math.PI + 90 // +90 т.к. стрелка вниз по умолчанию

        const nx = cx + dx * LERP
        const ny = cy + dy * LERP
        guideArrowPos.value = { x: nx, y: ny }

        // Добавить точку следа если сдвинулись достаточно
        const last = guideTrail.value[guideTrail.value.length - 1]
        const ldx = nx - (last?.x ?? nx)
        const ldy = ny - (last?.y ?? ny)
        if (Math.sqrt(ldx * ldx + ldy * ldy) > TRAIL_MIN_DIST) {
          guideTrail.value.push({ x: nx, y: ny })
          // Ограничим длину следа для производительности
          if (guideTrail.value.length > 500) guideTrail.value.shift()
        }

        if (dist < ARRIVE_DIST) {
          arrived = true
          guideArrowArrived.value = true
        }
      } else {
        // Прилипаем к полю (поле могло сдвинуться)
        guideArrowPos.value = _getDestCenter(el!)
      }

      _guideRafId = requestAnimationFrame(tick)
    }

    _guideRafId = requestAnimationFrame(tick)

    // Safety: убираем через 3 минуты
    _guideSafetyTimer = setTimeout(() => clearGuideArrow(), 3 * 60 * 1000)
  }

  return {
    guideArrowVisible, guideArrowPos, guideArrowAngle, guideArrowArrived, guideTrail,
    pointerTarget, okpd2Pointer, auctionPointerTarget,
    clearGuideArrow, guideArrowTo,
  }
}

