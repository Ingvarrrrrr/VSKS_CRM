// useWishColumnMenu.ts — конфигурация колонок (ColumnConfigDialog) + построчные
// фильтры/сортировка колонок (ColumnHeaderMenu, «B7») для трёх вкладок заявок.
// Дословный перенос из WishesView.vue, поведение не меняется.
import { computed, ref, type Ref } from 'vue'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'
import { wishRecipients, wishItemsTotal } from './useWishesContext'
import type { Wish } from './wishTypes'

// Table headers
const allWishColumns: ColumnDef[] = [
  { title: 'Статус', key: 'status', width: 110, sortable: true },
  // Владелец (30.09): номер и предмет заявки — разные сущности, раньше жили в одной
  // колонке «Заявка» (номер крупным текстом + предмет подписью). Номер — программный,
  // нередактируемый technical id, узкая колонка первой среди данных. group: 'core' —
  // чтобы колонка появилась и у пользователей с уже сохранённой раскладкой localStorage
  // (см. useColumnConfig.loadState: newCoreVisible).
  { title: 'Номер заявки', key: 'number_col', width: 90, sortable: true, group: 'core' },
  // Явный width (не только «резиновая» колонка без width): «Предмет заявки» —
  // единственная колонка без фикс. width, при добавлении «Суммы» ниже сумма фикс. width
  // колонок превысила типичную ширину экрана и она схлопывалась почти до нуля — текст
  // рвался по буквам в вертикальный столбик (Vuetify 3.11 minWidth в headers не действует
  // на раскладку th — проверено). Таблица уходит в горизонтальный скролл, как и
  // остальные широкие реестры проекта.
  { title: 'Предмет заявки', key: 'title_col', width: 260, sortable: false },
  { title: 'От кого', key: 'creator_name', width: 180, sortable: true },
  // «Кому» = назначенный (assigned_to) или цепочка согласующих — одно понятие
  { title: 'Кому', key: 'approver_names', width: 180, sortable: false },
  { title: 'Мероприятие', key: 'event_name', width: 180, sortable: true },
  // Владелец, 2026-09-02: subsidy_name уже приходит в WishOut (backend/app/schemas/wishes.py) —
  // просто вывести колонку.
  { title: 'Субсидия', key: 'subsidy_name', width: 180, sortable: true },
  // Владелец, 2026-08-13: сумма заявки (Σ total_price позиций) — как денежные колонки
  // в закупках (formatPrice), с сортировкой (соседние колонки тоже sortable).
  { title: 'Сумма', key: 'wish_total', width: 120, align: 'end' as const, sortable: true },
  { title: 'Создано', key: 'created_at', width: 110, sortable: true },
  { title: 'Срок', key: 'desired_date', width: 110, sortable: true },
  { title: 'Исполнитель', key: 'executor_name', width: 160, sortable: true },
  { title: 'Срок исп.', key: 'execution_deadline', width: 110, sortable: true },
  { title: 'Действия', key: 'actions', width: 160, sortable: false },
]

const EXCLUDED_WISH_KEYS = new Set(['actions', 'data-table-expand'])

export function useWishColumnMenu(options: {
  myWishes: Ref<Wish[]>
  incomingWishes: Ref<Wish[]>
  allWishes: Ref<Wish[]>
  activeTab: Ref<string>
}) {
  const { myWishes, incomingWishes, allWishes, activeTab } = options

  // Владелец, 2026-09-02: редактор колонок (выбор видимых + порядок + ширина) — ОДИН
  // набор настроек на все три вкладки заявок («Мои» / «На согласование мне» /
  // «Заявки сотрудников»): колонки везде одни и те же, раздельная настройка заставила
  // бы настраивать одно и то же трижды. Ключ localStorage 'wishes' (в паре с
  // v-resizable-columns, у которого свои ключи per-таб 'wishes-my' и т.п. — это
  // отдельный механизм ширины колонок при live-резайзе, не конфликтует).
  const {
    state: wishColState,
    visibleHeaders: wishVisibleHeaders,
    toggleVisible: wishToggleVisible,
    setPosition: wishSetPosition,
    setWidth: wishSetWidth,
    reset: wishResetColumns,
  } = useColumnConfig('wishes', allWishColumns)
  const showWishColumnPicker = ref(false)

  const wishHeaders = computed(() => wishVisibleHeaders.value)
  const wishHeadersAll = wishHeaders

  // Ключи колонок для UI (фильтр/сортировка) не всегда совпадают с реальными полями
  // Wish, которые уходит в тело экспорта (backend/app/services/report_excel.py делает
  // общий row.get(key)) — «number_col»/«title_col» виртуальные, реальные поля 'id'/'title'.
  const EXPORT_KEY_MAP: Record<string, string> = {
    number_col: 'id',
    title_col: 'title',
  }
  function getWishExportColumns() {
    // Экспорт не зависит от того, что пользователь скрыл в редакторе колонок —
    // как и раньше, выгружаем полный набор.
    return allWishColumns
      .filter(h => !EXCLUDED_WISH_KEYS.has(h.key) && h.title)
      .map(h => ({ key: EXPORT_KEY_MAP[h.key] ?? h.key, title: h.title, align: (h as any).align }))
  }
  function getWishExportRows() {
    if (activeTab.value === 'my') return myWishesFiltered.value
    if (activeTab.value === 'incoming') return incomingWishesFiltered.value
    return allWishesFiltered.value
  }

  // ── B7: ColumnHeaderMenu — per-column filter + sort ────────────────────
  const colFilters = ref<Record<string, any>>({
    status: null,
    number_col: null,
    title_col: null,
    creator_name: null,
    approver_names: null,
    event_name: null,
    subsidy_name: null,
    wish_total: null,
    created_at: null,
    desired_date: null,
    executor_name: null,
    execution_deadline: null,
  })
  const colSort = ref<Record<string, 'asc' | 'desc' | null>>({
    status: null,
    number_col: null,
    title_col: null,
    creator_name: null,
    approver_names: null,
    event_name: null,
    subsidy_name: null,
    wish_total: null,
    created_at: null,
    desired_date: null,
    executor_name: null,
    execution_deadline: null,
  })

  // Владелец, 2026-09-02: список значений для enum-фильтра колонки «Субсидия» — образец OrdersView.vue.
  function uniqWishValues(rows: Wish[], key: string): (string | number | null)[] {
    const set = new Set<any>()
    rows.forEach(r => set.add((r as any)?.[key] ?? null))
    return [...set].sort((a, b) => String(a ?? '').localeCompare(String(b ?? '')))
  }

  // ── Поиск (телефон, 2026-10-05): одно поле строкой в WishFilterPanel.vue —
  // «ввожу буквы, остаются только подходящие заявки». ПРАВИЛО №6 — не второй
  // конвейер фильтрации: ещё одно условие ВНУТРИ applyColFilters, работает на
  // всех трёх вкладках вместе с колоночными фильтрами/сортировкой. Локальный,
  // без запросов к серверу — applyColFilters уже вызывается на computed'ах ниже.
  const searchText = ref('')
  // ё=е, без учёта регистра, обрезка пробелов — как в поиске контрагентов проекта.
  function normalizeSearchText(s: string): string {
    return s.toLowerCase().replace(/ё/g, 'е').trim()
  }
  const searchWords = computed(() => {
    const q = normalizeSearchText(searchText.value)
    return q ? q.split(/\s+/).filter(Boolean) : []
  })
  // Один общий «мешок текста» на заявку — номер, предмет, автор+соавторы, кому
  // (согласующие/получатель), субсидия, мероприятие, исполнитель, номер реестра
  // закупки (свой + из w.purchases), сумма (цифрами без пробелов — «486000»
  // находит «486 000 ₽»). Хелперы те же, что уже используются в applyColFilters/
  // колонках ниже (wishRecipients/wishItemsTotal) — не дублируем вычисление суммы.
  function wishSearchHaystack(w: Wish): string {
    const parts: (string | null | undefined)[] = [
      String(w.id ?? ''), `№${w.id ?? ''}`,
      w.title, w.creator_name, ...(w.member_names || []),
      wishRecipients(w), w.assigned_to_name,
      (w as any).subsidy_name, (w as any).event_name, (w as any).executor_name,
      w.registry_number, ...((w.purchases || []).map(p => p.registry_number)),
    ]
    const sum = wishItemsTotal(w)
    if (sum != null) parts.push(String(Math.round(sum)))
    return normalizeSearchText(parts.filter(Boolean).join(' '))
  }
  function applySearch(rows: Wish[]): Wish[] {
    if (!searchWords.value.length) return [...rows]
    return rows.filter(r => {
      const hay = wishSearchHaystack(r)
      return searchWords.value.every(w => hay.includes(w))
    })
  }

  function applyColFilters(rows: Wish[]): Wish[] {
    let result = applySearch(rows)
    // text filters
    if (colFilters.value.number_col?.type === 'text' && colFilters.value.number_col.q)
      result = result.filter(r => String(r.id ?? '').includes(colFilters.value.number_col.q.trim()))
    if (colFilters.value.title_col?.type === 'text' && colFilters.value.title_col.q)
      result = result.filter(r => (r.title || '').toLowerCase().includes(colFilters.value.title_col.q.toLowerCase()))
    if (colFilters.value.creator_name?.type === 'text' && colFilters.value.creator_name.q)
      result = result.filter(r => [r.creator_name || '', ...(r.member_names || [])]
        .join(' ').toLowerCase().includes(colFilters.value.creator_name.q.toLowerCase()))
    if (colFilters.value.approver_names?.type === 'text' && colFilters.value.approver_names.q)
      result = result.filter(r => wishRecipients(r).toLowerCase().includes(colFilters.value.approver_names.q.toLowerCase()))
    if (colFilters.value.event_name?.type === 'text' && colFilters.value.event_name.q)
      result = result.filter(r => ((r as any).event_name || '').toLowerCase().includes(colFilters.value.event_name.q.toLowerCase()))
    if (colFilters.value.executor_name?.type === 'text' && colFilters.value.executor_name.q)
      result = result.filter(r => ((r as any).executor_name || '').toLowerCase().includes(colFilters.value.executor_name.q.toLowerCase()))
    // enum filter for status
    if (colFilters.value.status?.type === 'enum' && Array.isArray(colFilters.value.status.values) && colFilters.value.status.values.length)
      result = result.filter(r => colFilters.value.status.values.includes(r.status))
    // enum filter for subsidy_name
    if (colFilters.value.subsidy_name?.type === 'enum' && Array.isArray(colFilters.value.subsidy_name.values) && colFilters.value.subsidy_name.values.length)
      result = result.filter(r => colFilters.value.subsidy_name.values.includes((r as any).subsidy_name ?? null))
    // number filter for wish_total (сумма заявки)
    if (colFilters.value.wish_total?.type === 'number') {
      const { min, max } = colFilters.value.wish_total
      result = result.filter(r => {
        const v = wishItemsTotal(r)
        if (v == null) return false
        if (min != null && v < min) return false
        if (max != null && v > max) return false
        return true
      })
    }
    // sort: pick first active sort
    const activeSort = Object.entries(colSort.value).find(([_, v]) => v)
    if (activeSort) {
      const [k, dir] = activeSort
      if (k === 'wish_total') {
        result.sort((a, b) => {
          const va = wishItemsTotal(a) ?? -Infinity
          const vb = wishItemsTotal(b) ?? -Infinity
          return dir === 'asc' ? va - vb : vb - va
        })
      } else if (k === 'number_col') {
        // Номер заявки = Wish.id — сортировка числом, не строкой (localeCompare с
        // numeric:true ниже тоже справился бы, но id всегда целое число проще сравнить напрямую).
        result.sort((a: any, b: any) => {
          const va = a.id ?? -Infinity
          const vb = b.id ?? -Infinity
          return dir === 'asc' ? va - vb : vb - va
        })
      } else {
        result.sort((a: any, b: any) => {
          const pick = (r: any) => k === 'approver_names' ? wishRecipients(r) : r[k === 'title_col' ? 'title' : k]
          const va = pick(a) ?? ''
          const vb = pick(b) ?? ''
          const cmp = String(va).localeCompare(String(vb), 'ru', { numeric: true })
          return dir === 'asc' ? cmp : -cmp
        })
      }
    }
    return result
  }

  const myWishesFiltered = computed(() => applyColFilters(myWishes.value))
  const incomingWishesFiltered = computed(() => applyColFilters(incomingWishes.value))
  const allWishesFiltered = computed(() => applyColFilters(allWishes.value))

  // Владелец, 2026-09-02: варианты для enum-фильтра «Субсидия» — по данным активной вкладки
  // (colFilters/colSort общие на все три таба, шаблон ColumnHeaderMenu тоже один и тот же).
  const wishSubsidyNameOptions = computed(() => uniqWishValues(
    activeTab.value === 'my' ? myWishesFiltered.value
      : activeTab.value === 'incoming' ? incomingWishesFiltered.value
      : allWishesFiltered.value,
    'subsidy_name',
  ))

  return {
    allWishColumns,
    wishColState,
    wishToggleVisible,
    wishSetPosition,
    wishSetWidth,
    wishResetColumns,
    wishHeaders,
    wishHeadersAll,
    getWishExportColumns,
    getWishExportRows,
    colFilters,
    colSort,
    searchText,
    myWishesFiltered,
    incomingWishesFiltered,
    allWishesFiltered,
    wishSubsidyNameOptions,
    showWishColumnPicker,
  }
}
