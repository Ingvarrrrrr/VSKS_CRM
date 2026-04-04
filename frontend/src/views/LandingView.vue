<template>
  <div class="landing" :class="isDark ? 'landing-dark' : 'landing-light'">

    <!-- ═══ Navbar ═══ -->
    <header class="land-nav">
      <div class="land-nav-inner">
        <div class="land-logo">
          <v-icon icon="mdi-account-cash" color="primary" size="26" />
          <span>VSKS CRM</span>
        </div>
        <div class="land-nav-actions">
          <button class="theme-toggle" @click="toggleTheme" :title="isDark ? 'Светлая тема' : 'Тёмная тема'">
            <v-icon :icon="isDark ? 'mdi-weather-sunny' : 'mdi-weather-night'" size="18" />
          </button>
          <v-btn variant="text" size="small" to="/login" class="nav-btn-text">Войти</v-btn>
          <v-btn color="primary" variant="flat" size="small" to="/register" rounded="lg">
            Начать бесплатно
          </v-btn>
        </div>
      </div>
    </header>

    <!-- ═══ Hero ═══ -->
    <section class="hero">
      <!-- Decorative blobs -->
      <div class="blob blob-1" />
      <div class="blob blob-2" />
      <div class="blob blob-3" />

      <div class="hero-inner">
        <v-chip color="primary" variant="tonal" size="small" class="mb-5">
          <v-icon start icon="mdi-check-decagram" size="14" />
          Система управления государственными субсидиями
        </v-chip>

        <h1 class="hero-headline">
          Весь цикл субсидий —<br>
          <span class="headline-accent">в одном окне</span>
        </h1>

        <p class="hero-sub">
          Планируйте закупки, контролируйте бюджет, генерируйте документы
          и анализируйте исполнение — без Excel и бумажной волокиты.
        </p>

        <div class="hero-cta">
          <v-btn color="primary" size="large" to="/register" rounded="lg" elevation="0" class="cta-primary">
            Зарегистрировать организацию
            <v-icon end icon="mdi-arrow-right" />
          </v-btn>
          <v-btn size="large" variant="outlined" to="/login" rounded="lg" class="cta-secondary">
            Войти в систему
          </v-btn>
        </div>
        <p class="hero-hint">Регистрация 2 мин · Подтверждение по email · Бесплатно</p>

        <!-- ─── App mockup ─── -->
        <div class="mockup-wrap">
          <div class="mockup-browser">
            <!-- Chrome bar -->
            <div class="browser-chrome">
              <div class="chrome-dots">
                <span class="cd cd-r"/><span class="cd cd-y"/><span class="cd cd-g"/>
              </div>
              <div class="chrome-addr">vsks-crm.ru/dashboard</div>
              <div style="width:56px"/>
            </div>
            <!-- UI preview -->
            <div class="browser-body">
              <!-- Sidebar -->
              <div class="mock-sidebar">
                <div class="mock-logo-row">
                  <div class="mock-dot-logo" />
                  <div class="mock-line short" />
                </div>
                <div v-for="(active, i) in [true,false,false,false,false,false,false]" :key="i"
                  class="mock-nav-row" :class="active ? 'mock-nav-active' : ''">
                  <div class="mock-icon-sq" :style="active ? 'background:var(--clr-primary-op)' : ''" />
                  <div class="mock-line" :class="active ? 'mock-line-primary' : ''" />
                </div>
              </div>
              <!-- Main content -->
              <div class="mock-content">
                <!-- Header strip -->
                <div class="mock-topbar">
                  <div class="mock-line short" />
                  <div class="d-flex gap-1 ml-auto">
                    <div class="mock-badge" style="background:#dbeafe" />
                    <div class="mock-avatar" />
                  </div>
                </div>
                <!-- KPI row -->
                <div class="mock-kpi-row">
                  <div v-for="kpi in mockKpis" :key="kpi.label" class="mock-kpi">
                    <div class="mock-kpi-icon" :style="{ background: kpi.bg }">
                      <v-icon :icon="kpi.icon" size="12" color="white" />
                    </div>
                    <div class="mock-kpi-val">{{ kpi.val }}</div>
                    <div class="mock-kpi-lbl">{{ kpi.label }}</div>
                  </div>
                </div>
                <!-- Charts row -->
                <div class="mock-charts">
                  <div class="mock-chart-card" style="flex:2">
                    <div class="mock-card-title" />
                    <div class="mock-bars">
                      <div v-for="h in barHeights" :key="h" class="mock-bar" :style="{ height: h+'%' }" />
                    </div>
                    <div class="mock-bar-labels">
                      <div v-for="i in 6" :key="i" class="mock-line" style="width:24px" />
                    </div>
                  </div>
                  <div class="mock-chart-card" style="flex:1">
                    <div class="mock-card-title" />
                    <div class="mock-donut-wrap">
                      <div class="mock-donut" />
                      <div class="mock-donut-legend">
                        <div v-for="c in donutColors" :key="c" class="mock-legend-row">
                          <div class="mock-legend-dot" :style="{background: c}" />
                          <div class="mock-line" style="width:36px" />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                <!-- Table stub -->
                <div class="mock-table-card">
                  <div class="mock-card-title" />
                  <div v-for="i in 3" :key="i" class="mock-table-row">
                    <div class="mock-avatar sm" />
                    <div class="mock-line" />
                    <div class="mock-line short ml-auto" />
                    <div class="mock-badge" :style="{ background: ['#dcfce7','#fef3c7','#dbeafe'][i-1] }" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══ Stats strip ═══ -->
    <section class="stats-strip">
      <div class="stats-inner">
        <div v-for="stat in stats" :key="stat.label" class="stat-item">
          <div class="stat-val">{{ stat.val }}</div>
          <div class="stat-label">{{ stat.label }}</div>
        </div>
      </div>
    </section>

    <!-- ═══ For whom ═══ -->
    <section class="section-pad">
      <div class="section-container">
        <div class="section-header">
          <div class="section-eyebrow">Целевая аудитория</div>
          <h2 class="section-title">Создана для тех, кто работает с субсидиями</h2>
        </div>
        <div class="audience-grid">
          <div v-for="a in audiences" :key="a.title" class="audience-card">
            <div class="audience-icon" :style="{ background: a.grad }">
              <v-icon :icon="a.icon" color="white" size="22" />
            </div>
            <div class="audience-title">{{ a.title }}</div>
            <p class="audience-desc">{{ a.desc }}</p>
            <div class="audience-tags">
              <span v-for="t in a.tags" :key="t" class="tag">{{ t }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══ Features ═══ -->
    <section class="section-pad features-bg">
      <div class="section-container">
        <div class="section-header">
          <div class="section-eyebrow">Возможности</div>
          <h2 class="section-title">Полный цикл — от планирования до отчётности</h2>
          <p class="section-sub">Все инструменты в едином пространстве. Никакой лишней сложности.</p>
        </div>
        <div class="features-grid">
          <div v-for="f in features" :key="f.title" class="feat-card">
            <div class="feat-icon-wrap" :style="{ background: f.grad }">
              <v-icon :icon="f.icon" color="white" size="20" />
            </div>
            <div class="feat-title">{{ f.title }}</div>
            <p class="feat-desc">{{ f.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══ CTA ═══ -->
    <section class="section-pad">
      <div class="section-container">
        <div class="cta-block">
          <div class="cta-glow" />
          <div class="section-eyebrow light">Начните сегодня</div>
          <h2 class="section-title light">Готовы автоматизировать работу с субсидиями?</h2>
          <p class="section-sub light">
            Зарегистрируйте организацию — и уже через 2 минуты начните работу.
          </p>
          <div class="hero-cta mt-8">
            <v-btn color="white" size="large" to="/register" rounded="lg" elevation="0"
              style="color: #1E40AF; font-weight: 700">
              Зарегистрироваться бесплатно
              <v-icon end icon="mdi-arrow-right" />
            </v-btn>
            <v-btn size="large" variant="outlined" to="/login" rounded="lg"
              style="border-color: rgba(255,255,255,0.4); color: white">
              Войти
            </v-btn>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══ Footer ═══ -->
    <footer class="land-footer">
      <div class="section-container">
        <div class="footer-inner">
          <div class="land-logo">
            <v-icon icon="mdi-account-cash" color="primary" size="20" />
            <span style="font-size:14px">VSKS CRM</span>
          </div>
          <span class="footer-copy">© {{ year }} Патриотика — Управление государственными субсидиями</span>
        </div>
      </div>
    </footer>

  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useTheme } from 'vuetify'

const vuetifyTheme = useTheme()
const isDark = computed(() => vuetifyTheme.global.name.value === 'dark')
const year = new Date().getFullYear()

function toggleTheme() {
  const next = isDark.value ? 'light' : 'dark'
  vuetifyTheme.global.name.value = next
  localStorage.setItem('theme', next)
}

const mockKpis = [
  { icon: 'mdi-cash-multiple', bg: '#2563EB', val: '₽ 12.4М', label: 'Бюджет' },
  { icon: 'mdi-clipboard-check', bg: '#059669', val: '48', label: 'Закупок' },
  { icon: 'mdi-file-document', bg: '#D97706', val: '23', label: 'Документов' },
  { icon: 'mdi-trending-up', bg: '#7C3AED', val: '94%', label: 'Выполнено' },
]
const barHeights = [55, 78, 42, 90, 63, 81]
const donutColors = ['#2563EB', '#059669', '#D97706', '#7C3AED']

const stats = [
  { val: '₽ 500М+', label: 'Бюджетов под управлением' },
  { val: '200+', label: 'Успешных закупок' },
  { val: '98%', label: 'Довольных организаций' },
  { val: '3 мин', label: 'Среднее время на документ' },
]

const audiences = [
  {
    title: 'Государственные учреждения',
    icon: 'mdi-bank-outline',
    grad: 'linear-gradient(135deg, #1E40AF, #3B82F6)',
    desc: 'Ведите несколько субсидий одновременно. Бюджетный контроль и отчётность в реальном времени.',
    tags: ['Субсидии', 'Бюджет', 'Отчётность'],
  },
  {
    title: 'Менеджеры закупок',
    icon: 'mdi-account-tie-outline',
    grad: 'linear-gradient(135deg, #065F46, #10B981)',
    desc: 'Полный workflow закупки: от запроса КП до подписания контракта. Документы — в один клик.',
    tags: ['Закупки', 'Документы', 'Workflow'],
  },
  {
    title: 'Финансовые отделы',
    icon: 'mdi-chart-line-variant',
    grad: 'linear-gradient(135deg, #5B21B6, #8B5CF6)',
    desc: 'Аналитика, дерево ФЭО, план-факт анализ. Вся картина исполнения бюджета на одном экране.',
    tags: ['Аналитика', 'ФЭО', 'KPI'],
  },
]

const features = [
  {
    title: 'Управление субсидиями', icon: 'mdi-cash-multiple',
    grad: 'linear-gradient(135deg, #1D4ED8, #3B82F6)',
    desc: 'Создавайте субсидии, задавайте бюджеты, отслеживайте статусы. Поддержка нескольких субсидий параллельно.',
  },
  {
    title: 'Закупочный процесс', icon: 'mdi-clipboard-list-outline',
    grad: 'linear-gradient(135deg, #047857, #10B981)',
    desc: 'Статусный workflow: планирование → контракт → поставка → оплата. Контроль превышения бюджета.',
  },
  {
    title: 'Генерация документов', icon: 'mdi-file-document-edit-outline',
    grad: 'linear-gradient(135deg, #B45309, #F59E0B)',
    desc: 'Листы согласования, служебные записки, договоры — автоматически из данных системы по шаблонам DOCX.',
  },
  {
    title: 'Дерево ФЭО', icon: 'mdi-folder-tree',
    grad: 'linear-gradient(135deg, #5B21B6, #8B5CF6)',
    desc: 'Иерархическое финансово-экономическое обоснование с привязкой бюджета к каждой категории.',
  },
  {
    title: 'Аналитика и дашборд', icon: 'mdi-chart-areaspline',
    grad: 'linear-gradient(135deg, #0E7490, #06B6D4)',
    desc: 'KPI-карточки, графики расходов, структура закупок, сравнение план/факт — в реальном времени.',
  },
  {
    title: 'Мультиорганизационность', icon: 'mdi-domain',
    grad: 'linear-gradient(135deg, #9D174D, #EC4899)',
    desc: 'Несколько организаций в одной системе. Роли: org_admin / manager / employee. Полная изоляция данных.',
  },
]
</script>

<style scoped>
/* ══════ VARIABLES ══════ */
.landing-light {
  --bg:        #FFFFFF;
  --bg-2:      #F8FAFC;
  --surface:   #FFFFFF;
  --border:    rgba(0,0,0,0.08);
  --text:      #0F172A;
  --text-2:    #475569;
  --text-3:    #94A3B8;
  --nav-bg:    rgba(255,255,255,0.85);
  --stats-bg:  #F1F5F9;
  --feat-bg:   #F8FAFC;
  --card-bg:   #FFFFFF;
  --clr-primary-op: rgba(37,99,235,0.1);
  --mock-bg:   #F1F5F9;
  --mock-line: rgba(0,0,0,0.1);
  --mock-line-2: rgba(0,0,0,0.05);
  --browser-bg: #FFFFFF;
}
.landing-dark {
  --bg:        #030712;
  --bg-2:      #0F172A;
  --surface:   #111827;
  --border:    rgba(255,255,255,0.08);
  --text:      #F1F5F9;
  --text-2:    #94A3B8;
  --text-3:    #475569;
  --nav-bg:    rgba(3,7,18,0.85);
  --stats-bg:  #0F172A;
  --feat-bg:   #0F172A;
  --card-bg:   #111827;
  --clr-primary-op: rgba(96,165,250,0.15);
  --mock-bg:   #1E293B;
  --mock-line: rgba(255,255,255,0.15);
  --mock-line-2: rgba(255,255,255,0.07);
  --browser-bg: #1E293B;
}

/* ══════ BASE ══════ */
.landing {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  transition: background .3s, color .3s;
}

/* ══════ NAVBAR ══════ */
.land-nav {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--nav-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
  padding: 0 24px;
  height: 60px;
  display: flex;
  align-items: center;
}
.land-nav-inner {
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.land-logo {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
}
.land-nav-actions { display: flex; align-items: center; gap: 8px; }
.nav-btn-text { color: var(--text-2) !important; }
.theme-toggle {
  width: 36px; height: 36px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: transparent;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: var(--text-2);
  transition: background .2s, border-color .2s;
}
.theme-toggle:hover { background: var(--bg-2); border-color: var(--text-3); }

/* ══════ HERO ══════ */
.hero {
  position: relative;
  overflow: hidden;
  padding: 80px 24px 0;
  background: var(--bg);
}
.blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.35;
  animation: float 8s ease-in-out infinite;
  pointer-events: none;
}
.blob-1 {
  width: 500px; height: 500px;
  background: radial-gradient(circle, #3B82F6, transparent);
  top: -120px; left: -80px;
  animation-delay: 0s;
}
.blob-2 {
  width: 400px; height: 400px;
  background: radial-gradient(circle, #8B5CF6, transparent);
  top: 0px; right: -80px;
  animation-delay: -3s;
}
.blob-3 {
  width: 300px; height: 300px;
  background: radial-gradient(circle, #06B6D4, transparent);
  bottom: 100px; left: 40%;
  animation-delay: -6s;
}
@keyframes float {
  0%, 100% { transform: translateY(0) scale(1); }
  50% { transform: translateY(-30px) scale(1.05); }
}
.landing-dark .blob { opacity: 0.2; }

.hero-inner {
  position: relative;
  z-index: 1;
  max-width: 900px;
  margin: 0 auto;
  text-align: center;
}
.hero-headline {
  font-size: clamp(2.2rem, 5.5vw, 4rem);
  font-weight: 800;
  line-height: 1.12;
  letter-spacing: -0.02em;
  margin-bottom: 24px;
  color: var(--text);
}
.headline-accent {
  background: linear-gradient(135deg, #2563EB, #7C3AED);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.hero-sub {
  font-size: 1.1rem;
  color: var(--text-2);
  max-width: 560px;
  margin: 0 auto 36px;
  line-height: 1.65;
}
.hero-cta {
  display: flex;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}
.cta-primary { box-shadow: 0 0 0 4px rgba(37,99,235,0.15) !important; }
.hero-hint {
  font-size: 12px;
  color: var(--text-3);
  margin-top: 16px;
}

/* ══════ MOCKUP ══════ */
.mockup-wrap {
  margin-top: 56px;
  perspective: 1000px;
}
.mockup-browser {
  max-width: 860px;
  margin: 0 auto;
  border-radius: 12px 12px 0 0;
  overflow: hidden;
  border: 1px solid var(--border);
  border-bottom: none;
  box-shadow:
    0 32px 80px rgba(0,0,0,0.18),
    0 0 0 1px var(--border);
  background: var(--browser-bg);
  transform: rotateX(4deg);
  transform-origin: top center;
}
.browser-chrome {
  background: var(--bg-2);
  border-bottom: 1px solid var(--border);
  padding: 10px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.chrome-dots { display: flex; gap: 5px; }
.cd { width: 11px; height: 11px; border-radius: 50%; display: block; }
.cd-r { background: #FF5F57; }
.cd-y { background: #FFBD2E; }
.cd-g { background: #28CA41; }
.chrome-addr {
  flex: 1;
  height: 22px;
  background: var(--bg);
  border-radius: 6px;
  font-size: 11px;
  color: var(--text-3);
  display: flex;
  align-items: center;
  padding: 0 10px;
  border: 1px solid var(--border);
}
.browser-body { display: flex; height: 240px; background: var(--browser-bg); }

/* Sidebar */
.mock-sidebar {
  width: 52px;
  background: var(--bg-2);
  border-right: 1px solid var(--border);
  padding: 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.mock-logo-row { display: flex; align-items: center; gap: 4px; margin-bottom: 8px; }
.mock-dot-logo { width: 16px; height: 16px; border-radius: 4px; background: #2563EB; flex-shrink: 0; }
.mock-nav-row { display: flex; align-items: center; gap: 4px; padding: 4px; border-radius: 5px; }
.mock-nav-active { background: var(--clr-primary-op); }
.mock-icon-sq { width: 14px; height: 14px; border-radius: 3px; background: var(--mock-line-2); flex-shrink: 0; }
.mock-content {
  flex: 1;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
}
/* Common line/element */
.mock-line { height: 6px; border-radius: 3px; background: var(--mock-line); flex: 1; }
.mock-line.short { max-width: 80px; }
.mock-line-primary { background: #2563EB !important; }
.mock-badge { width: 32px; height: 14px; border-radius: 10px; background: #dbeafe; }
.mock-avatar { width: 22px; height: 22px; border-radius: 50%; background: var(--mock-line); flex-shrink: 0; }
.mock-avatar.sm { width: 16px; height: 16px; border-radius: 4px; }

.mock-topbar { display: flex; align-items: center; gap: 6px; }

/* KPI */
.mock-kpi-row { display: flex; gap: 6px; }
.mock-kpi {
  flex: 1;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.mock-kpi-icon { width: 20px; height: 20px; border-radius: 5px; display: flex; align-items: center; justify-content: center; }
.mock-kpi-val { font-size: 11px; font-weight: 700; color: var(--text); }
.mock-kpi-lbl { font-size: 8px; color: var(--text-3); }

/* Charts */
.mock-charts { display: flex; gap: 6px; flex: 1; overflow: hidden; }
.mock-chart-card {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow: hidden;
}
.mock-card-title { height: 6px; border-radius: 3px; background: var(--mock-line); width: 60%; }
.mock-bars { display: flex; align-items: flex-end; gap: 3px; flex: 1; }
.mock-bar {
  flex: 1;
  background: linear-gradient(to top, #2563EB 0%, #93C5FD 100%);
  border-radius: 2px 2px 0 0;
  min-height: 4px;
}
.mock-bar-labels { display: flex; gap: 3px; }
.mock-donut-wrap { display: flex; align-items: center; gap: 8px; flex: 1; }
.mock-donut {
  width: 44px; height: 44px;
  border-radius: 50%;
  background: conic-gradient(#2563EB 0% 35%, #059669 35% 60%, #D97706 60% 80%, #7C3AED 80% 100%);
  flex-shrink: 0;
}
.mock-donut-legend { display: flex; flex-direction: column; gap: 4px; flex: 1; }
.mock-legend-row { display: flex; align-items: center; gap: 4px; }
.mock-legend-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }

/* Table */
.mock-table-card {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.mock-table-row { display: flex; align-items: center; gap: 6px; }

/* ══════ STATS ══════ */
.stats-strip {
  background: var(--stats-bg);
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  padding: 36px 24px;
}
.stats-inner {
  max-width: 900px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 24px;
  text-align: center;
}
.stat-val {
  font-size: 2rem;
  font-weight: 800;
  background: linear-gradient(135deg, #2563EB, #7C3AED);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: -0.02em;
}
.stat-label { font-size: 13px; color: var(--text-2); margin-top: 4px; }

/* ══════ SECTIONS ══════ */
.section-pad { padding: 80px 24px; background: var(--bg); }
.features-bg { background: var(--feat-bg); }
.section-container { max-width: 1100px; margin: 0 auto; }
.section-header { text-align: center; margin-bottom: 56px; }
.section-eyebrow {
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #3B82F6;
  margin-bottom: 14px;
}
.section-eyebrow.light { color: rgba(255,255,255,0.7); }
.section-title {
  font-size: clamp(1.6rem, 3.5vw, 2.4rem);
  font-weight: 800;
  line-height: 1.2;
  letter-spacing: -0.02em;
  color: var(--text);
  margin-bottom: 16px;
}
.section-title.light { color: white; }
.section-sub { font-size: 1rem; color: var(--text-2); max-width: 500px; margin: 0 auto; }
.section-sub.light { color: rgba(255,255,255,0.7); }

/* ══════ AUDIENCES ══════ */
.audience-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}
.audience-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 28px;
  transition: border-color .2s, transform .2s, box-shadow .2s;
}
.audience-card:hover {
  border-color: #3B82F6;
  transform: translateY(-3px);
  box-shadow: 0 12px 32px rgba(37,99,235,0.12);
}
.audience-icon {
  width: 48px; height: 48px;
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  margin-bottom: 18px;
}
.audience-title { font-size: 1rem; font-weight: 700; color: var(--text); margin-bottom: 10px; }
.audience-desc { font-size: 14px; color: var(--text-2); line-height: 1.6; margin-bottom: 16px; }
.audience-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.tag {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 20px;
  background: rgba(37,99,235,0.08);
  color: #3B82F6;
  font-weight: 500;
}
.landing-dark .tag { background: rgba(96,165,250,0.12); color: #93C5FD; }

/* ══════ FEATURES ══════ */
.features-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}
.feat-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 28px;
  transition: border-color .2s, transform .2s, box-shadow .2s;
}
.feat-card:hover {
  border-color: transparent;
  transform: translateY(-3px);
  box-shadow: 0 12px 32px rgba(0,0,0,0.1);
}
.feat-icon-wrap {
  width: 44px; height: 44px;
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  margin-bottom: 16px;
}
.feat-title { font-size: 15px; font-weight: 700; color: var(--text); margin-bottom: 8px; }
.feat-desc { font-size: 13px; color: var(--text-2); line-height: 1.6; }

/* ══════ CTA BLOCK ══════ */
.cta-block {
  position: relative;
  background: linear-gradient(135deg, #1E40AF 0%, #5B21B6 50%, #1E40AF 100%);
  background-size: 200% 200%;
  animation: gradshift 6s ease infinite;
  border-radius: 24px;
  padding: 72px 48px;
  text-align: center;
  overflow: hidden;
}
.cta-glow {
  position: absolute;
  inset: -50%;
  background: radial-gradient(ellipse at 50% 50%, rgba(139,92,246,0.4), transparent 60%);
  pointer-events: none;
}
@keyframes gradshift {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}

/* ══════ FOOTER ══════ */
.land-footer {
  padding: 24px;
  border-top: 1px solid var(--border);
  background: var(--bg);
}
.footer-inner {
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.footer-copy { font-size: 12px; color: var(--text-3); }

/* ══════ RESPONSIVE ══════ */
@media (max-width: 768px) {
  .audience-grid, .features-grid { grid-template-columns: 1fr; }
  .stats-inner { grid-template-columns: repeat(2, 1fr); }
  .hero-headline { font-size: 2rem; }
  .mockup-browser { display: none; }
  .hero { padding-bottom: 60px; }
  .cta-block { padding: 48px 24px; }
}
@media (max-width: 600px) {
  .stats-inner { grid-template-columns: repeat(2, 1fr); }
  .land-nav .land-nav-actions :nth-child(2) { display: none; }
}
</style>
