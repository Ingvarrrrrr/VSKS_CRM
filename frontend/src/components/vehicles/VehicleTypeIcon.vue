<template>
  <!-- Flat side-profile silhouette icon for vehicle type.
       fill="currentColor" — inherits CSS color from parent.
       Wheels drawn as circles with a lighter inner circle.
  -->
  <svg
    :viewBox="meta.viewBox"
    :width="size"
    :height="Math.round(size * meta.aspect)"
    fill="currentColor"
    xmlns="http://www.w3.org/2000/svg"
    :class="$attrs.class"
    aria-hidden="true"
  >
    <g v-html="meta.path" />
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  type?: string
  /** Base width in px. Height scales by aspect ratio. Default 60 */
  size?: number
}>()

const size = computed(() => props.size ?? 60)

interface IconMeta {
  viewBox: string
  aspect: number  // height / width
  path: string    // raw SVG inner markup
}

// All silhouettes are flat, side-profile, fill=currentColor.
// viewBox origin top-left. Wheels use two circles (outer dark, inner slightly lighter via opacity).
const ICONS: Record<string, IconMeta> = {

  // ── Sedan / light car ────────────────────────────────────────────────────────
  car_light: {
    viewBox: '0 0 100 42',
    aspect: 42 / 100,
    path: `
      <!-- body -->
      <path d="M8 32 L10 24 Q14 16 26 14 L44 13 Q58 13 66 18 L86 24 L90 30 L90 32 Z"/>
      <!-- cabin roof -->
      <path d="M24 14 Q28 6 40 6 L56 6 Q68 6 72 14 Z" opacity=".72"/>
      <!-- windscreen cutout (dark glass) -->
      <path d="M28 14 L32 8 L42 8 L42 14 Z" opacity=".35" style="mix-blend-mode:multiply"/>
      <path d="M44 8 L58 8 L64 14 L44 14 Z" opacity=".35" style="mix-blend-mode:multiply"/>
      <!-- wheels -->
      <circle cx="24" cy="34" r="7"/>
      <circle cx="24" cy="34" r="3" opacity=".3"/>
      <circle cx="72" cy="34" r="7"/>
      <circle cx="72" cy="34" r="3" opacity=".3"/>
    `,
  },

  // ── Minivan ──────────────────────────────────────────────────────────────────
  minivan: {
    viewBox: '0 0 96 44',
    aspect: 44 / 96,
    path: `
      <!-- body: tall, short front -->
      <path d="M8 34 L10 20 Q14 10 26 10 L80 10 Q90 10 90 20 L90 34 Z"/>
      <!-- windows row -->
      <rect x="14" y="13" width="16" height="10" rx="2" opacity=".35"/>
      <rect x="34" y="13" width="16" height="10" rx="2" opacity=".35"/>
      <rect x="54" y="13" width="16" height="10" rx="2" opacity=".35"/>
      <rect x="74" y="13" width="10" height="10" rx="2" opacity=".35"/>
      <!-- wheels -->
      <circle cx="24" cy="36" r="7"/>
      <circle cx="24" cy="36" r="3" opacity=".3"/>
      <circle cx="72" cy="36" r="7"/>
      <circle cx="72" cy="36" r="3" opacity=".3"/>
    `,
  },

  // ── Cargo van (фургон) ───────────────────────────────────────────────────────
  truck_van: {
    viewBox: '0 0 100 44',
    aspect: 44 / 100,
    path: `
      <!-- box body -->
      <rect x="4" y="10" width="58" height="26" rx="2"/>
      <!-- cab -->
      <rect x="62" y="18" width="28" height="18" rx="2"/>
      <!-- cab window -->
      <rect x="65" y="20" width="20" height="9" rx="1" opacity=".35"/>
      <!-- wheels -->
      <circle cx="18" cy="38" r="6"/>
      <circle cx="18" cy="38" r="2.5" opacity=".3"/>
      <circle cx="44" cy="38" r="6"/>
      <circle cx="44" cy="38" r="2.5" opacity=".3"/>
      <circle cx="80" cy="38" r="6"/>
      <circle cx="80" cy="38" r="2.5" opacity=".3"/>
    `,
  },

  // ── Board truck (бортовой) ───────────────────────────────────────────────────
  truck_board: {
    viewBox: '0 0 110 46',
    aspect: 46 / 110,
    path: `
      <!-- cab -->
      <rect x="70" y="16" width="32" height="22" rx="2"/>
      <!-- cab window -->
      <rect x="74" y="18" width="20" height="10" rx="1" opacity=".35"/>
      <!-- flatbed platform -->
      <rect x="4" y="26" width="68" height="6" rx="1"/>
      <!-- platform side stakes -->
      <rect x="8" y="18" width="3" height="8" rx="1"/>
      <rect x="20" y="18" width="3" height="8" rx="1"/>
      <rect x="32" y="18" width="3" height="8" rx="1"/>
      <rect x="44" y="18" width="3" height="8" rx="1"/>
      <rect x="56" y="18" width="3" height="8" rx="1"/>
      <!-- wheels -->
      <circle cx="18" cy="38" r="7"/>
      <circle cx="18" cy="38" r="3" opacity=".3"/>
      <circle cx="50" cy="38" r="7"/>
      <circle cx="50" cy="38" r="3" opacity=".3"/>
      <circle cx="86" cy="38" r="7"/>
      <circle cx="86" cy="38" r="3" opacity=".3"/>
      <circle cx="100" cy="38" r="7"/>
      <circle cx="100" cy="38" r="3" opacity=".3"/>
    `,
  },

  // ── Tank truck (цистерна) ────────────────────────────────────────────────────
  truck_tank: {
    viewBox: '0 0 110 46',
    aspect: 46 / 110,
    path: `
      <!-- cab -->
      <rect x="72" y="16" width="30" height="22" rx="2"/>
      <rect x="76" y="18" width="18" height="10" rx="1" opacity=".35"/>
      <!-- tank cylinder (ellipse body) -->
      <ellipse cx="38" cy="26" rx="36" ry="14"/>
      <!-- tank end caps -->
      <ellipse cx="4" cy="26" rx="4" ry="14"/>
      <ellipse cx="72" cy="26" rx="4" ry="14"/>
      <!-- wheels -->
      <circle cx="20" cy="40" r="6"/>
      <circle cx="20" cy="40" r="2.5" opacity=".3"/>
      <circle cx="54" cy="40" r="6"/>
      <circle cx="54" cy="40" r="2.5" opacity=".3"/>
      <circle cx="88" cy="40" r="6"/>
      <circle cx="88" cy="40" r="2.5" opacity=".3"/>
    `,
  },

  // ── Metal carrier (металловоз / флэт) ────────────────────────────────────────
  truck_metal: {
    viewBox: '0 0 110 46',
    aspect: 46 / 110,
    path: `
      <!-- cab -->
      <rect x="72" y="16" width="30" height="22" rx="2"/>
      <rect x="76" y="18" width="18" height="10" rx="1" opacity=".35"/>
      <!-- flat platform -->
      <rect x="4" y="27" width="70" height="5" rx="1"/>
      <!-- metal load beams (horizontal) -->
      <rect x="8" y="20" width="60" height="3" rx="1" opacity=".75"/>
      <rect x="8" y="24" width="60" height="2" rx="1" opacity=".5"/>
      <!-- wheels -->
      <circle cx="20" cy="38" r="7"/>
      <circle cx="20" cy="38" r="3" opacity=".3"/>
      <circle cx="52" cy="38" r="7"/>
      <circle cx="52" cy="38" r="3" opacity=".3"/>
      <circle cx="88" cy="38" r="7"/>
      <circle cx="88" cy="38" r="3" opacity=".3"/>
    `,
  },

  // ── Bus (автобус) ────────────────────────────────────────────────────────────
  bus: {
    viewBox: '0 0 110 44',
    aspect: 44 / 110,
    path: `
      <!-- body -->
      <rect x="4" y="8" width="102" height="28" rx="4"/>
      <!-- windows row -->
      <rect x="8"  y="12" width="12" height="9" rx="2" opacity=".35"/>
      <rect x="24" y="12" width="12" height="9" rx="2" opacity=".35"/>
      <rect x="40" y="12" width="12" height="9" rx="2" opacity=".35"/>
      <rect x="56" y="12" width="12" height="9" rx="2" opacity=".35"/>
      <rect x="72" y="12" width="12" height="9" rx="2" opacity=".35"/>
      <rect x="88" y="12" width="12" height="9" rx="2" opacity=".35"/>
      <!-- wheels -->
      <circle cx="22" cy="38" r="6"/>
      <circle cx="22" cy="38" r="2.5" opacity=".3"/>
      <circle cx="86" cy="38" r="6"/>
      <circle cx="86" cy="38" r="2.5" opacity=".3"/>
    `,
  },

  // ── Special / crane (спецтехника) ────────────────────────────────────────────
  special: {
    viewBox: '0 0 100 52',
    aspect: 52 / 100,
    path: `
      <!-- base vehicle body -->
      <rect x="4" y="22" width="56" height="22" rx="2"/>
      <!-- cab -->
      <rect x="60" y="26" width="30" height="18" rx="2"/>
      <rect x="64" y="28" width="18" height="9" rx="1" opacity=".35"/>
      <!-- crane boom base -->
      <rect x="22" y="14" width="8" height="10" rx="1" opacity=".85"/>
      <!-- crane boom arm -->
      <path d="M26 14 L44 4 L46 6 L28 16 Z" opacity=".75"/>
      <!-- hook line -->
      <line x1="44" y1="5" x2="44" y2="14" stroke-width="1.5" stroke="currentColor" opacity=".6"/>
      <!-- wheels -->
      <circle cx="18" cy="46" r="6"/>
      <circle cx="18" cy="46" r="2.5" opacity=".3"/>
      <circle cx="44" cy="46" r="6"/>
      <circle cx="44" cy="46" r="2.5" opacity=".3"/>
      <circle cx="76" cy="46" r="6"/>
      <circle cx="76" cy="46" r="2.5" opacity=".3"/>
    `,
  },

  // ── Quadbike (квадроцикл) ────────────────────────────────────────────────────
  quadbike: {
    viewBox: '0 0 80 46',
    aspect: 46 / 80,
    path: `
      <!-- seat/body block -->
      <rect x="24" y="16" width="32" height="12" rx="5"/>
      <!-- handlebars -->
      <rect x="50" y="10" width="6" height="10" rx="3"/>
      <!-- front forks -->
      <path d="M52 18 L56 30" stroke-width="3" stroke="currentColor" fill="none"/>
      <!-- rear -->
      <path d="M28 26 L22 30" stroke-width="3" stroke="currentColor" fill="none"/>
      <!-- front wheel -->
      <circle cx="60" cy="34" r="10"/>
      <circle cx="60" cy="34" r="4" opacity=".3"/>
      <!-- rear wheel -->
      <circle cx="18" cy="34" r="10"/>
      <circle cx="18" cy="34" r="4" opacity=".3"/>
    `,
  },

  // ── Snowmobile (снегоход) ────────────────────────────────────────────────────
  snowmobile: {
    viewBox: '0 0 100 44',
    aspect: 44 / 100,
    path: `
      <!-- body hood -->
      <path d="M12 26 L18 14 L52 14 L62 22 L62 28 L12 28 Z"/>
      <!-- windshield -->
      <path d="M20 14 L24 8 L40 8 L44 14 Z" opacity=".4"/>
      <!-- seat / tail -->
      <rect x="8" y="22" width="58" height="6" rx="3"/>
      <!-- ski (front) -->
      <path d="M2 32 Q4 36 20 36 L24 36" stroke-width="3" stroke="currentColor" fill="none" stroke-linecap="round"/>
      <!-- track belt (rear, elongated) -->
      <rect x="10" y="30" width="52" height="10" rx="5" opacity=".6"/>
      <!-- drive wheel rear -->
      <circle cx="72" cy="30" r="10"/>
      <circle cx="72" cy="30" r="4" opacity=".3"/>
    `,
  },

  // ── Boat (лодка) ────────────────────────────────────────────────────────────
  boat: {
    viewBox: '0 0 96 44',
    aspect: 44 / 96,
    path: `
      <!-- hull -->
      <path d="M8 26 Q8 18 18 18 L72 18 Q84 18 86 26 L82 36 Q48 40 14 36 Z"/>
      <!-- windscreen / bow -->
      <path d="M26 18 L30 10 L52 10 L56 18 Z" opacity=".5"/>
      <rect x="30" y="8" width="22" height="5" rx="2" opacity=".8"/>
    `,
  },

  // ── Boat with outboard motor (лодка с мотором) ───────────────────────────────
  boat_motor: {
    viewBox: '0 0 100 46',
    aspect: 46 / 100,
    path: `
      <!-- hull -->
      <path d="M8 28 Q8 20 18 20 L72 20 Q82 20 84 28 L80 38 Q46 42 14 38 Z"/>
      <!-- windscreen -->
      <path d="M26 20 L30 12 L52 12 L56 20 Z" opacity=".5"/>
      <rect x="30" y="10" width="22" height="5" rx="2" opacity=".8"/>
      <!-- outboard motor shaft -->
      <rect x="80" y="24" width="6" height="14" rx="2"/>
      <!-- propeller -->
      <path d="M77 38 Q83 42 90 38" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round"/>
    `,
  },

  // ── Trailer (прицеп) ─────────────────────────────────────────────────────────
  trailer: {
    viewBox: '0 0 96 44',
    aspect: 44 / 96,
    path: `
      <!-- trailer box -->
      <rect x="14" y="12" width="72" height="24" rx="2"/>
      <!-- coupling bar (дышло) -->
      <path d="M6 24 L14 24" stroke-width="3" stroke="currentColor" fill="none" stroke-linecap="round"/>
      <!-- coupling pin -->
      <circle cx="6" cy="24" r="3"/>
      <!-- ventilation slats -->
      <rect x="20" y="18" width="10" height="5" rx="1" opacity=".4"/>
      <rect x="36" y="18" width="10" height="5" rx="1" opacity=".4"/>
      <rect x="52" y="18" width="10" height="5" rx="1" opacity=".4"/>
      <rect x="68" y="18" width="10" height="5" rx="1" opacity=".4"/>
      <!-- wheels -->
      <circle cx="32" cy="38" r="6"/>
      <circle cx="32" cy="38" r="2.5" opacity=".3"/>
      <circle cx="62" cy="38" r="6"/>
      <circle cx="62" cy="38" r="2.5" opacity=".3"/>
    `,
  },

  // ── Other / generic fallback ──────────────────────────────────────────────────
  other: {
    viewBox: '0 0 100 42',
    aspect: 42 / 100,
    path: `
      <!-- body (generic SUV-like) -->
      <path d="M8 34 L10 24 Q14 16 28 14 L46 13 Q58 13 68 18 L88 26 L90 30 L90 34 Z"/>
      <!-- cabin roof -->
      <path d="M26 14 Q30 7 42 7 L58 7 Q68 7 74 14 Z" opacity=".72"/>
      <!-- windows -->
      <path d="M30 14 L34 8 L44 8 L44 14 Z" opacity=".35"/>
      <path d="M46 8 L58 8 L64 14 L46 14 Z" opacity=".35"/>
      <!-- wheels -->
      <circle cx="26" cy="36" r="7"/>
      <circle cx="26" cy="36" r="3" opacity=".3"/>
      <circle cx="72" cy="36" r="7"/>
      <circle cx="72" cy="36" r="3" opacity=".3"/>
    `,
  },
}

// Fallback chain: exact type → 'other'
const meta = computed<IconMeta>(() => {
  const t = props.type || ''
  return ICONS[t] ?? ICONS['other']
})
</script>
