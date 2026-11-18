// Опциональный мягкий саундтрек сборки через Web Audio API (без аудиофайлов).
// По умолчанию ВЫКЛЮЧЕН — включается пользователем и сохраняется в localStorage.

const SOUND_KEY = 'gala_swarm_sound'

let audioCtx: AudioContext | null = null

export function isSwarmSoundEnabled(): boolean {
  try {
    return localStorage.getItem(SOUND_KEY) === '1'
  } catch {
    return false
  }
}

export function setSwarmSoundEnabled(enabled: boolean): void {
  try {
    localStorage.setItem(SOUND_KEY, enabled ? '1' : '0')
  } catch {}
}

function getCtx(): AudioContext | null {
  if (typeof window === 'undefined') return null
  const Ctor = window.AudioContext || (window as any).webkitAudioContext
  if (!Ctor) return null
  if (!audioCtx) {
    try {
      audioCtx = new Ctor()
    } catch {
      return null
    }
  }
  if (audioCtx.state === 'suspended') {
    audioCtx.resume().catch(() => {})
  }
  return audioCtx
}

/** Мягкий щелчок «прилипания» блока при сборке. */
export function playSwarmSnapSound(stepIndex = 0): void {
  if (!isSwarmSoundEnabled()) return
  const ctx = getCtx()
  if (!ctx) return
  try {
    const now = ctx.currentTime
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    const notes = [392, 440, 493.88, 523.25, 587.33, 659.25]
    osc.type = 'sine'
    osc.frequency.setValueAtTime(notes[stepIndex % notes.length], now)
    gain.gain.setValueAtTime(0.0001, now)
    gain.gain.exponentialRampToValueAtTime(0.025, now + 0.015)
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.11)
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start(now)
    osc.stop(now + 0.12)
  } catch {}
}

/** Короткий тёплый аккорд по завершению сборки экрана. */
export function playSwarmCompleteSound(): void {
  if (!isSwarmSoundEnabled()) return
  const ctx = getCtx()
  if (!ctx) return
  try {
    const now = ctx.currentTime
    const chord = [523.25, 659.25, 783.99]
    chord.forEach((freq, idx) => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'triangle'
      osc.frequency.setValueAtTime(freq, now + idx * 0.03)
      gain.gain.setValueAtTime(0.0001, now + idx * 0.03)
      gain.gain.exponentialRampToValueAtTime(0.018, now + idx * 0.03 + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, now + idx * 0.03 + 0.22)
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.start(now + idx * 0.03)
      osc.stop(now + idx * 0.03 + 0.24)
    })
  } catch {}
}
