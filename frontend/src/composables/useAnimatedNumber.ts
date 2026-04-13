import { ref, watch, type Ref } from 'vue'

function easeOutExpo(t: number): number {
  return t === 1 ? 1 : 1 - Math.pow(2, -10 * t)
}

export function useAnimatedNumber(target: Ref<number>, duration = 1000): Ref<number> {
  const display = ref(0)
  let animId = 0

  watch(target, (newVal, oldVal) => {
    cancelAnimationFrame(animId)
    const start = display.value
    const diff = newVal - start
    if (diff === 0) return
    const startTime = performance.now()

    function tick(now: number) {
      const elapsed = now - startTime
      const progress = Math.min(elapsed / duration, 1)
      display.value = Math.round(start + diff * easeOutExpo(progress))
      if (progress < 1) {
        animId = requestAnimationFrame(tick)
      } else {
        display.value = newVal
      }
    }
    animId = requestAnimationFrame(tick)
  }, { immediate: true })

  return display
}

export function useAnimatedNumbers(
  targets: Record<string, Ref<number>>,
  duration = 1000
): Record<string, Ref<number>> {
  const result: Record<string, Ref<number>> = {}
  for (const key in targets) {
    result[key] = useAnimatedNumber(targets[key], duration)
  }
  return result
}
