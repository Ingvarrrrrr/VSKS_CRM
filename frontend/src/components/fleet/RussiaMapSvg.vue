<template>
  <div class="russia-map" :class="{ 'russia-map--light': !isDark }">
    <svg viewBox="0 0 600 360" xmlns="http://www.w3.org/2000/svg">
      <!-- Russia schematic outline (from regions.html) -->
      <path
        d="M40,180 Q60,140 110,130 Q160,118 220,124 Q280,130 340,138 Q420,150 500,162 Q540,172 560,200 Q540,240 470,250 Q380,260 290,255 Q200,250 130,242 Q70,232 40,210 Z"
        :fill="contourFill"
        :stroke="contourStroke"
        stroke-width="1.5"
        stroke-dasharray="4 4"
        opacity="0.6"
      />

      <!-- Grid background -->
      <defs>
        <pattern id="grid-bg" width="24" height="24" patternUnits="userSpaceOnUse">
          <path d="M 24 0 L 0 0 0 24" fill="none" :stroke="contourStroke" stroke-width="0.4" opacity="0.35"/>
        </pattern>
      </defs>
      <rect width="600" height="360" fill="url(#grid-bg)" opacity="0.5" rx="12"/>

      <!-- Connecting lines (transfers between HQs) -->
      <g v-if="connections.length">
        <line
          v-for="(c, i) in connections"
          :key="`conn-${i}`"
          :x1="c.from.x"
          :y1="c.from.y"
          :x2="c.to.x"
          :y2="c.to.y"
          :stroke="contourStroke"
          stroke-width="1.2"
          stroke-dasharray="3 3"
          opacity="0.4"
        />
      </g>
      <!-- Default connections when no override provided -->
      <g v-else>
        <line x1="180" y1="200" x2="155" y2="250" stroke="#6aa6ff" stroke-width="1" stroke-dasharray="3 3" opacity=".4"/>
        <line x1="155" y1="200" x2="190" y2="275" stroke="#6aa6ff" stroke-width="1" stroke-dasharray="3 3" opacity=".4"/>
        <line x1="155" y1="250" x2="170" y2="290" stroke="#6aa6ff" stroke-width="1" stroke-dasharray="3 3" opacity=".4"/>
        <line x1="155" y1="250" x2="140" y2="265" stroke="#6aa6ff" stroke-width="1" stroke-dasharray="3 3" opacity=".4"/>
        <line x1="180" y1="200" x2="450" y2="200" stroke="#6aa6ff" stroke-width="1" stroke-dasharray="3 3" opacity=".4"/>
      </g>

      <!-- Pins via props (or default pins when none passed) -->
      <g
        v-for="pin in activePins"
        :key="pin.id"
        class="pin-grp"
        :transform="`translate(${pin.x},${pin.y})`"
        @click="$emit('pin-click', pin)"
      >
        <!-- Halo -->
        <circle :r="pin.radius + 6" :fill="pin.color" opacity="0.2"/>
        <!-- Main circle -->
        <circle :r="pin.radius" :fill="pin.color" :stroke="pinStroke" stroke-width="1.5"/>
        <!-- Count inside -->
        <text
          text-anchor="middle"
          dominant-baseline="central"
          :fill="pin.textColor || '#0a0d14'"
          :font-size="Math.max(8, pin.radius * 0.75)"
          font-weight="700"
          font-family="JetBrains Mono, monospace"
        >{{ pin.count }}</text>
        <!-- Label above pin -->
        <text
          v-if="pin.name"
          text-anchor="middle"
          :y="-(pin.radius + 10)"
          :fill="labelColor"
          font-size="11"
          font-weight="600"
          font-family="Inter, system-ui, sans-serif"
        >{{ pin.name }}</text>
        <!-- Sub-label below pin -->
        <text
          v-if="pin.sub"
          text-anchor="middle"
          :y="pin.radius + 14"
          :fill="mutedColor"
          font-size="10"
          font-family="Inter, system-ui, sans-serif"
        >{{ pin.sub }}</text>
      </g>

      <!-- SVG inline legend (visible inside SVG canvas) -->
      <g transform="translate(20,330)">
        <circle cx="6" cy="0" r="5" fill="#6aa6ff"/><text x="16" y="3" font-size="10" :fill="mutedColor" font-family="Inter, sans-serif">штаб</text>
        <circle cx="64" cy="0" r="5" fill="#f6b34a"/><text x="74" y="3" font-size="10" :fill="mutedColor" font-family="Inter, sans-serif">СТО/ремонт</text>
        <circle cx="158" cy="0" r="5" fill="#22c997"/><text x="168" y="3" font-size="10" :fill="mutedColor" font-family="Inter, sans-serif">регион эксп.</text>
        <circle cx="248" cy="0" r="5" fill="#8b5cf6"/><text x="258" y="3" font-size="10" :fill="mutedColor" font-family="Inter, sans-serif">ФПГ-источник</text>
      </g>
    </svg>

    <!-- HTML legend below map -->
    <div class="russia-map__legend">
      <span class="leg-item"><i class="leg-dot" style="background:#6aa6ff"></i>Штаб</span>
      <span class="leg-item"><i class="leg-dot" style="background:#f6b34a"></i>СТО</span>
      <span class="leg-item"><i class="leg-dot" style="background:#22c997"></i>Регион эксплуатации</span>
      <span class="leg-item"><i class="leg-dot" style="background:#8b5cf6"></i>ФПГ-источник</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useTheme } from 'vuetify'

export interface MapPin {
  id: string | number
  name?: string
  sub?: string
  x: number
  y: number
  radius: number
  count: number
  color: string  // '#6aa6ff' (blue/штаб) | '#f6b34a' (warn/СТО) | '#22c997' (ok/регион) | '#8b5cf6' (purple/ФПГ)
  textColor?: string
}

export interface MapConnection {
  from: { x: number; y: number }
  to: { x: number; y: number }
}

/** Default pins extracted from regions.html etalon */
export const DEFAULT_PINS: MapPin[] = [
  { id: 'msk',     name: 'ЦУ Москва',       sub: '9 ТС · штаб',      x: 180, y: 200, radius: 16, count: 9,  color: '#6aa6ff' },
  { id: 'rnd',     name: 'Ростов-на-Дону',  sub: '18 ТС · СТО',      x: 155, y: 250, radius: 22, count: 18, color: '#f6b34a' },
  { id: 'lnr',     name: 'Луганск (ЛНР)',   sub: '',                  x: 190, y: 275, radius: 12, count: 6,  color: '#22c997' },
  { id: 'dnr',     name: 'Донецк (ДНР)',    sub: '',                  x: 170, y: 290, radius: 11, count: 5,  color: '#22c997' },
  { id: 'zp',      name: 'Запорожье',       sub: '',                  x: 140, y: 265, radius: 9,  count: 4,  color: '#8b5cf6' },
  { id: 'kursk',   name: 'Курск',           sub: '',                  x: 160, y: 225, radius: 8,  count: 2,  color: '#5dd0ff' },
  { id: 'belg',    name: '',                sub: '',                  x: 170, y: 235, radius: 6,  count: 1,  color: '#5dd0ff' },
  { id: 'irk',     name: 'Иркутск',         sub: '3 ТС · ФПГ',       x: 450, y: 200, radius: 9,  count: 3,  color: '#8b5cf6' },
  { id: 'tula',    name: '',                sub: '',                  x: 195, y: 210, radius: 5,  count: 1,  color: '#5dd0ff' },
  { id: 'crimea',  name: 'Крым',            sub: '',                  x: 115, y: 275, radius: 5,  count: 1,  color: '#5dd0ff' },
  { id: 'kherson', name: '',                sub: '',                  x: 125, y: 290, radius: 5,  count: 1,  color: '#5dd0ff' },
]

const props = withDefaults(defineProps<{
  pins?: MapPin[]
  connections?: MapConnection[]
}>(), {
  pins: () => [],
  connections: () => [],
})

defineEmits<{
  (e: 'pin-click', pin: MapPin): void
}>()

const theme = useTheme()
const isDark = computed(() => theme.global.current.value.dark)

const contourFill   = computed(() => isDark.value ? 'rgba(106,166,255,0.04)' : 'rgba(106,166,255,0.08)')
const contourStroke = computed(() => isDark.value ? 'rgba(106,166,255,0.18)' : 'rgba(106,166,255,0.35)')
const pinStroke     = computed(() => isDark.value ? '#0a0d14' : '#ffffff')
const labelColor    = computed(() => isDark.value ? '#e9edf5' : '#1a1d23')
const mutedColor    = computed(() => isDark.value ? '#8a93a8' : '#6b7280')

// Use provided pins or fall back to etalon defaults
const activePins = computed(() => props.pins.length ? props.pins : DEFAULT_PINS)
</script>

<style scoped>
.russia-map {
  position: relative;
  width: 100%;
  background: transparent;
  border-radius: 14px;
}

.russia-map svg {
  width: 100%;
  height: auto;
  display: block;
  border-radius: 12px;
  background:
    radial-gradient(circle at 60% 50%, rgba(106,166,255,.04), transparent 70%),
    linear-gradient(180deg, rgba(255,255,255,.02), rgba(255,255,255,0));
  border: 1px solid rgba(106,166,255,.1);
}

.russia-map--light svg {
  background:
    radial-gradient(circle at 60% 50%, rgba(106,166,255,.06), transparent 70%),
    #f5f7fa;
  border-color: #e2e6f0;
}

.pin-grp {
  cursor: pointer;
  transition: transform 0.15s ease;
}

.pin-grp:hover {
  transform: scale(1.12);
}

.russia-map__legend {
  display: flex;
  gap: 16px;
  padding: 10px 16px;
  flex-wrap: wrap;
  font-size: 12px;
}

.leg-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: currentColor;
  opacity: 0.75;
}

.leg-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}
</style>
