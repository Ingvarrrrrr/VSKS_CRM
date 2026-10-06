// «Где превышение» — жалоба владельца 06.10.2026, дословно: «мне предлагается
// подтвердить превышение, при этом я не могу посмотреть что это за
// превышение, надо чтобы была возможность нажать и посмотреть что это за
// превышения, чтобы раскрылась субсидия и стрелочки привели к каждому пункту
// превышения». Клик по чипу превышения ПО ТИПУ (SubsidyKpiCards.vue — уровень
// субсидии, FeoTreeRow.vue — уровень категории, оба уже рисуют этот чип, см.
// useFeoTreeExcess.ts::typeExcessFor/TYPE_EXCESS_KIND_DEFS) находит самые
// глубокие статьи дерева ФЭО, у которых именно этот вид превышения больше
// нуля, раскрывает их предков и подсвечивает стрелками (PointerArrow.vue в
// FeoTreeRow.vue) + панелью навигации (ExcessDrilldownBar.vue).
//
// Доработка по приёмке 06.10.2026 (субсидия «ФАДМ 2026_2», id 7320): узловой
// контроль (excessTargetIds) бывает 0 ВЕЗДЕ, когда ФЭО по типу целиком лежит
// без разбивки на одной категории (например, «Не определена»), а план по
// типу разложен по другим направлениям — главный случай владельца. Для этого
// случая — РЕЗЕРВНЫЙ режим compositionTargetIds (см. её докстринг ниже),
// панель переключается на него сама (activate()), когда excessTargetIds пуст.
//
// excessTargetIds/compositionTargetIds/excessTargetsTotal/excessDiffLine —
// ЧИСТЫЕ функции: читают уже посчитанные бэкендом поля узла (NODE_EXCESS_FIELD
// и обычные plan_X/feo_X/fact_X из PlanTreeEntry, useFeoTreeExcess.ts — тот же
// источник, что и чип), НЕ считают превышение заново (Правило №6). Вынесены
// отдельно от состояния composable, чтобы их можно было протестировать без
// Vue/ctx — см. __tests__/useExcessDrilldown.spec.ts. METRIC_FIELDS — ОДНА
// карта слов/полей по виду превышения (задание: «подписи видов/метрик — из
// TYPE_EXCESS_KIND_DEFS и одной локальной карты метрик, не россыпью строк»).
//
// Раскрытие предков — общий хелпер feoTreeAncestors.ts (тот же, что у
// useKpiDrilldown.ts, не копия). Взаимное гашение «KPI-подсветка/где
// превышение» — через activeHighlightMode (useHighlightMode.ts), чтобы не
// заводить циклический импорт между этим файлом и useKpiDrilldown.ts.
//
// Module-level singleton, как useKpiDrilldown.ts/useFeoTreeExcess.ts —
// SubsidiesView.vue строит с полным ctx первым, FeoTreeRow.vue/
// SubsidyKpiCards.vue/ExcessDrilldownBar.vue переиспользуют вызовом без
// аргумента (makeCtxSingleton, см. её докстринг в ctxSingleton.ts).
import { computed, nextTick, ref, watch, type Ref } from 'vue'
import { makeCtxSingleton } from './ctxSingleton'
import { buildFeoAncestors } from './feoTreeAncestors'
import { activeHighlightMode } from './useHighlightMode'
import { NODE_EXCESS_FIELD, TYPE_EXCESS_KIND_DEFS } from './useFeoTreeExcess'
import { formatCurrency } from './format'
import type { FeoCategory, PlanTreeEntry, SubsidyTypeTotals, TypeExcessKind } from './types'

export interface ExcessDrilldownCtx {
  feoCategories: Ref<FeoCategory[]>
  planTreeByCat: Ref<Record<number, PlanTreeEntry>>
  expandedIds: Ref<number[]>
  feoTableArea: Ref<HTMLElement | null>
  selectedId: Ref<number | null>
}

function amountOfField(entry: PlanTreeEntry | undefined, field: string): number {
  return Number((entry as any)?.[field] || 0)
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

// Единственная карта «какие два поля PlanTreeEntry сравнивает этот вид
// превышения, и какими словами их называть по-русски» — читают и
// compositionTargetIds/excessDiffLine здесь, и ExcessDrilldownBar.vue (список
// статей, Дефект 2 приёмки 06.10.2026). Не копируем isGoods/isPlanOverFeo по
// разным функциям (было до этой правки — Правило №6).
export const METRIC_FIELDS: Record<TypeExcessKind, {
  upperField: 'plan_goods' | 'plan_services' | 'fact_goods' | 'fact_services'
  lowerField: 'feo_goods' | 'feo_services' | 'plan_goods' | 'plan_services'
  upperWord: string; lowerWord: string; lowerWordGen: string; typeWord: string
}> = {
  plan_over_feo_goods:     { upperField: 'plan_goods',   lowerField: 'feo_goods',    upperWord: 'план',    lowerWord: 'ФЭО',  lowerWordGen: 'ФЭО',   typeWord: 'товарам' },
  plan_over_feo_services:  { upperField: 'plan_services', lowerField: 'feo_services', upperWord: 'план',    lowerWord: 'ФЭО',  lowerWordGen: 'ФЭО',   typeWord: 'услугам' },
  fact_over_plan_goods:    { upperField: 'fact_goods',   lowerField: 'plan_goods',   upperWord: 'закупки', lowerWord: 'план', lowerWordGen: 'плана', typeWord: 'товарам' },
  fact_over_plan_services: { upperField: 'fact_services', lowerField: 'plan_services', upperWord: 'закупки', lowerWord: 'план', lowerWordGen: 'плана', typeWord: 'услугам' },
}

function buildTreeIndex(categories: Pick<FeoCategory, 'id' | 'parent_id'>[]) {
  const knownIds = new Set(categories.map(c => c.id))
  const childrenOf: Record<number, number[]> = {}
  const roots: number[] = []
  for (const c of categories) {
    if (c.parent_id != null && knownIds.has(c.parent_id)) {
      (childrenOf[c.parent_id] ??= []).push(c.id)
    } else {
      roots.push(c.id)
    }
  }
  return { roots, childrenOf }
}

// Самые глубокие статьи-виновники: у узла САМОГО поле вида kind > 0, но ни у
// ОДНОГО его потомка (по parent_id) то же поле не > 0 — узлы дерева хранят
// АГРЕГАТ поддерева (backend/app/services/feo_plan_tree.py, см. задание), так
// что родитель, у которого превышает только ребёнок, сам не виновник, только
// переносчик суммы. Порядок результата — сверху вниз (pre-order от корней, в
// порядке исходного массива categories на каждом уровне — тот же порядок,
// что строит feoTree в useFeoTreeState.ts).
export function excessTargetIds(
  categories: Pick<FeoCategory, 'id' | 'parent_id'>[],
  planTreeByCat: Record<number, PlanTreeEntry>,
  kind: TypeExcessKind,
): number[] {
  const field = NODE_EXCESS_FIELD[kind]
  const amountOf = (id: number) => amountOfField(planTreeByCat[id], field)
  const { roots, childrenOf } = buildTreeIndex(categories)

  function hasExcessDescendant(id: number): boolean {
    for (const childId of childrenOf[id] || []) {
      if (amountOf(childId) > 0.005) return true
      if (hasExcessDescendant(childId)) return true
    }
    return false
  }

  const ids: number[] = []
  function visit(id: number) {
    if (amountOf(id) > 0.005 && !hasExcessDescendant(id)) ids.push(id)
    for (const childId of childrenOf[id] || []) visit(childId)
  }
  roots.forEach(visit)
  return ids
}

// РЕЗЕРВНЫЙ режим (приёмка 06.10.2026, субсидия «ФАДМ 2026_2», id 7320):
// excessTargetIds() выше пуст, когда узловой контроль по типу = 0 ВЕЗДЕ — это
// бывает, если ФЭО по типу целиком лежит без разбивки на одной категории
// (например, «Не определена»), а план по типу разложен по другим
// направлениям: на каждом отдельном узле «план − ФЭО» не превышает, хотя по
// субсидии в целом превышение реально есть (видно в subsidy_type_totals).
// compositionTargetIds НЕ ищет виновника — показывает корневые направления,
// из которых складывается верхняя (план/закупки) ЛИБО нижняя (ФЭО/план)
// величина, чтобы стрелка указала и туда, где лежит план, и туда, где лежит
// ФЭО, даже если это разные направления. Только корни (уровень агрегации в
// задаче владельца), порядок — как в массиве categories.
export function compositionTargetIds(
  categories: Pick<FeoCategory, 'id' | 'parent_id'>[],
  planTreeByCat: Record<number, PlanTreeEntry>,
  kind: TypeExcessKind,
): number[] {
  const { upperField, lowerField } = METRIC_FIELDS[kind]
  const { roots } = buildTreeIndex(categories)
  return roots.filter(id => {
    const entry = planTreeByCat[id]
    return amountOfField(entry, upperField) > 0.005 || amountOfField(entry, lowerField) > 0.005
  })
}

// Сумма превышения по найденным целям (excessTargetIds) — для подписи панели
// навигации и для excessDiffLine ниже. Отдельная маленькая функция, не внутри
// excessTargetIds, чтобы саму excessTargetIds было легко проверить тестом по
// одному только списку id (как и просит задание).
export function excessTargetsTotal(ids: number[], planTreeByCat: Record<number, PlanTreeEntry>, kind: TypeExcessKind): number {
  const field = NODE_EXCESS_FIELD[kind]
  return ids.reduce((sum, id) => sum + amountOfField(planTreeByCat[id], field), 0)
}

// Дефект 3 приёмки 06.10.2026: сумма превышения НАЙДЕННЫХ статей-виновников
// не обязана совпадать с итоговой суммой чипа субсидии целиком — у чипа своя
// формула (вся субсидия), а в остальных, не попавших в targets статьях
// закупки/план могут быть НИЖЕ план/ФЭО и гасить часть суммы в итоге. chipAmount
// читается готовым (subsidy_type_excess[kind].amount через typeExcessFor,
// Правило №6 — не пересчитываем контроль, только объясняем разницу словами).
// null — суммы совпали (с точностью до копейки), строку не показываем.
export function excessDiffLine(
  ids: number[],
  planTreeByCat: Record<number, PlanTreeEntry>,
  kind: TypeExcessKind,
  chipAmount: number,
): string | null {
  const sumTargets = excessTargetsTotal(ids, planTreeByCat, kind)
  const delta = sumTargets - chipAmount
  if (Math.abs(delta) <= 0.005) return null
  const { upperWord, lowerWordGen } = METRIC_FIELDS[kind]
  const direction = delta > 0 ? 'ниже' : 'выше'
  return `по этим статьям превышение ${formatCurrency(sumTargets)}; в остальных статьях ${upperWord} ${direction} ${lowerWordGen} на ${formatCurrency(Math.abs(delta))} — в итоге субсидии ${formatCurrency(chipAmount)}`
}

export const useExcessDrilldown = makeCtxSingleton(
  buildExcessDrilldown,
  'useExcessDrilldown() вызван до первого построения (нужен ctx) — проверьте порядок монтирования SubsidiesView.vue',
)

function buildExcessDrilldown(ctx: ExcessDrilldownCtx) {
  const { feoAncestorIds } = buildFeoAncestors(ctx.feoCategories)

  const activeKind = ref<TypeExcessKind | null>(null)
  const targets = ref<number[]>([])
  const currentIndex = ref(0)
  // true — targets построены резервным режимом compositionTargetIds (см. её
  // докстринг выше), а не настоящим виновником excessTargetIds. Панель
  // (ExcessDrilldownBar.vue) показывает другой заголовок в этом случае.
  const isComposition = ref(false)
  // Непусто только когда ПУСТ даже compositionTargetIds — превышение есть
  // только в сумме субсидии, и нет вообще ни одной статьи ни с планом/
  // закупками, ни с ФЭО по этому виду (данных по типу нет совсем).
  const emptyMessage = ref<string | null>(null)
  // Непусто в режиме compositionTargetIds — объясняет, почему стрелки стоят
  // не на «виновнике», а на статьях, из которых просто складывается итог.
  const compositionMessage = ref<string | null>(null)

  const kindLabel = computed(() => TYPE_EXCESS_KIND_DEFS.find(d => d.kind === activeKind.value)?.label ?? '')
  const activeMetric = computed(() => activeKind.value ? METRIC_FIELDS[activeKind.value] : null)
  const targetsTotal = computed(() => activeKind.value ? excessTargetsTotal(targets.value, ctx.planTreeByCat.value, activeKind.value) : 0)
  const currentTargetId = computed<number | null>(() => targets.value[currentIndex.value] ?? null)
  const hasTargets = computed(() => targets.value.length > 0)

  function subsidyTotals(): SubsidyTypeTotals | undefined {
    return (ctx.planTreeByCat.value as any)?.subsidy_type_totals as SubsidyTypeTotals | undefined
  }
  function subsidyChipAmount(kind: TypeExcessKind): number {
    const summary = (ctx.planTreeByCat.value as any)?.subsidy_type_excess as Record<TypeExcessKind, { amount: number }> | undefined
    return Number(summary?.[kind]?.amount ?? 0)
  }

  // Строка-разница для НОРМАЛЬНОГО режима (excessTargetIds, не composition) —
  // Дефект 3 приёмки.
  const diffLine = computed<string | null>(() => {
    if (!activeKind.value || isComposition.value || !targets.value.length) return null
    return excessDiffLine(targets.value, ctx.planTreeByCat.value, activeKind.value, subsidyChipAmount(activeKind.value))
  })

  // Совсем пусто — нет ни виновника, ни статей для composition-режима (нет
  // данных по типу вообще).
  function buildEmptyMessage(kind: TypeExcessKind): string {
    const amount = subsidyChipAmount(kind)
    return `по отдельным статьям превышения нет — превышение только в итоге субсидии целиком, на ${formatCurrency(amount)}`
  }

  // Дефект 1 приёмки 06.10.2026 — заголовок панели для composition-режима.
  // «ФЭО (или план) по направлениям не разнесено» — только если нижняя
  // величина сосредоточена на ОДНОМ корне, или лежит на корнях, где верхней
  // величины вовсе нет (не смешана с планом на одном и том же направлении);
  // иначе — нейтральная формулировка (задание, п.1, уточнение в скобках).
  function buildCompositionMessage(kind: TypeExcessKind): string {
    const { upperField, lowerField, upperWord, lowerWord, typeWord } = METRIC_FIELDS[kind]
    const totals = subsidyTotals()
    const upperTotal = totals ? Number(totals[upperField] || 0) : 0
    const lowerTotal = totals ? Number(totals[lowerField] || 0) : 0
    const { roots } = buildTreeIndex(ctx.feoCategories.value)
    const lowerRoots = roots.filter(id => amountOfField(ctx.planTreeByCat.value[id], lowerField) > 0.005)
    const concentrated = lowerRoots.length === 1
      || lowerRoots.every(id => amountOfField(ctx.planTreeByCat.value[id], upperField) <= 0.005)
    const tail = concentrated
      ? `${capitalize(lowerWord)} по ${typeWord} по направлениям не разнесено — стрелками показаны статьи, где лежит ${upperWord} и где лежит ${lowerWord}.`
      : 'Стрелками показаны статьи, из которых складывается итог.'
    return `Превышение только в итоге субсидии: ${upperWord} по ${typeWord} ${formatCurrency(upperTotal)} при ${lowerWord} по ${typeWord} ${formatCurrency(lowerTotal)}. ${tail}`
  }

  async function scrollToTarget(id: number | null) {
    if (id == null) return
    await nextTick()
    const el = ctx.feoTableArea.value?.querySelector(`[data-feo-node-id="${id}"]`) as HTMLElement | null
    if (!el) return
    // РЕГРЕСС (вторая приёмка 06.10.2026): ручной расчёт через
    // container.getBoundingClientRect()/scrollTo (прошлая версия этой
    // функции) скроллил ТОЛЬКО .feo-table-wrap — внутренний контейнер дерева
    // ФЭО. Само дерево обычно ниже KPI-карточек/чипов превышения, вне
    // видимой области страницы, а страницу (window/.v-main) та версия не
    // докручивала вовсе — клик по чипу/«Где?»/‹ › переставал прокручивать
    // куда-либо. el.scrollIntoView() докручивает ВСЕ прокручиваемые предки
    // по цепочке (включая window) сам — самый надёжный вариант, вместо
    // ручного обхода «найти реально прокручиваемого предка». block:'start' +
    // scrollMarginTop — тот же приём, что решал предыдущий (desktop)
    // дефект — цель в верхней трети экрана, под запасом на липкую шапку
    // таблицы (FeoTreeTable.vue :: .feo-th, position:sticky; top:0), а не по
    // центру под плавающей панелью (ExcessDrilldownBar.vue).
    el.style.scrollMarginTop = '160px'
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  function activate(kind: TypeExcessKind) {
    if (activeKind.value === kind) { clear(); return }
    activeKind.value = kind
    activeHighlightMode.value = 'excess' // гасит активную KPI-подсветку, см. useHighlightMode.ts

    let ids = excessTargetIds(ctx.feoCategories.value, ctx.planTreeByCat.value, kind)
    let composition = false
    if (ids.length === 0) {
      // Главный случай владельца (Дефект 1): узловой контроль 0 везде —
      // переключаемся на composition-режим, вместо молчаливой пустой панели.
      ids = compositionTargetIds(ctx.feoCategories.value, ctx.planTreeByCat.value, kind)
      composition = true
    }
    isComposition.value = composition
    targets.value = ids
    currentIndex.value = 0

    if (ids.length === 0) {
      emptyMessage.value = buildEmptyMessage(kind)
      compositionMessage.value = null
      return
    }
    emptyMessage.value = null
    compositionMessage.value = composition ? buildCompositionMessage(kind) : null

    // Раскрываем предков ВСЕХ целей разом — иначе next()/prev() упёрлись бы
    // в свёрнутую ветку соседней статьи.
    const toExpand = new Set(ctx.expandedIds.value)
    for (const id of ids) for (const a of feoAncestorIds(id)) toExpand.add(a)
    ctx.expandedIds.value = [...toExpand]
    scrollToTarget(ids[0])
  }

  function next() {
    if (!targets.value.length) return
    currentIndex.value = (currentIndex.value + 1) % targets.value.length
    scrollToTarget(currentTargetId.value)
  }

  function prev() {
    if (!targets.value.length) return
    currentIndex.value = (currentIndex.value - 1 + targets.value.length) % targets.value.length
    scrollToTarget(currentTargetId.value)
  }

  function goTo(index: number) {
    if (index < 0 || index >= targets.value.length) return
    currentIndex.value = index
    scrollToTarget(currentTargetId.value)
  }

  function clear() {
    activeKind.value = null
    targets.value = []
    currentIndex.value = 0
    isComposition.value = false
    emptyMessage.value = null
    compositionMessage.value = null
    if (activeHighlightMode.value === 'excess') activeHighlightMode.value = null
  }

  // Активировали KPI-плитку (useKpiDrilldown.ts) — гасим себя.
  watch(activeHighlightMode, (mode) => {
    if (mode !== 'excess' && activeKind.value) clear()
  })
  // Смена субсидии — просто сброс, без восстановления (как у useKpiDrilldown.ts).
  watch(ctx.selectedId, () => clear())

  // Читает FeoTreeRow.vue — класс строки/нужна ли стрелка. Работает
  // одинаково для обычного и composition-режима (targets — один и тот же
  // массив id независимо от того, как он был построен).
  function isExcessTarget(nodeId: number): boolean {
    return activeKind.value != null && targets.value.includes(nodeId)
  }
  function isCurrentExcessTarget(nodeId: number): boolean {
    return activeKind.value != null && currentTargetId.value === nodeId
  }

  // Дефект 2 приёмки 06.10.2026: список статей в панели — ОБА числа вида
  // (план/ФЭО или закупки/план) + превышение по статье, если оно есть (поле
  // NODE_EXCESS_FIELD самого узла — ноль в composition-режиме, где виновника
  // по отдельности нет, это и показывает пользователю честно). Имя статьи —
  // из feoCategories, тот же массив, что строит дерево (Правило №6).
  function targetRows(): { id: number; name: string; upper: number; lower: number; excess: number }[] {
    if (!activeKind.value) return []
    const { upperField, lowerField } = METRIC_FIELDS[activeKind.value]
    const excessField = NODE_EXCESS_FIELD[activeKind.value]
    return targets.value.map(id => {
      const entry = ctx.planTreeByCat.value[id]
      return {
        id,
        name: ctx.feoCategories.value.find(c => c.id === id)?.name || `#${id}`,
        upper: amountOfField(entry, upperField),
        lower: amountOfField(entry, lowerField),
        excess: amountOfField(entry, excessField),
      }
    })
  }

  return {
    activeKind, targets, currentIndex, emptyMessage, compositionMessage, isComposition, diffLine,
    kindLabel, activeMetric, targetsTotal, hasTargets, currentTargetId,
    activate, next, prev, goTo, clear, targetRows,
    isExcessTarget, isCurrentExcessTarget,
  }
}
