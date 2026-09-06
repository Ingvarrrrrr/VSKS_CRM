// Состояние и логика диалога «Добавить плановую позицию» (+ «перенести ручной
// план категории в позицию» + «завести из конкретной закупки») —
// PlannedItemAddDialog.vue. Один из четырёх кусков панели «План vs факт» ФЭО,
// вынесенных из SubsidiesView.vue (см. usePlannedItems.ts — баррель,
// объединяющий этот файл с остальными тремя; разнесены по файлам, чтобы не
// собирать один composable на 700+ строк — Правило №5, модульность кода).
// Module-level singleton state.
import { computed, ref, watch } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { numOrNull } from '@/utils/numberFormat'
import type { MatchCandidate } from '@/composables/useItemMatching'
import { leftGroupInfo } from './feoCategoryUtils'
import type { SubsidyDetailContext } from './useSubsidyDetail'
import type { FeoActualItem, FeoNode, FeoPlannedItem } from './types'

const showAddPlannedDialog = ref(false)
const addPlannedCategoryId = ref<number | null>(null)
const savingPlannedItem = ref(false)
// Флаг «эта позиция заводится действием "Перенести в плановую позицию"» (не обычной
// кнопкой «Добавить плановую») — savePlannedItem после успешного создания по нему
// очищает planned_quantity/planned_amount категории (см. ниже), иначе поля категории
// продолжают заслонять созданную запись в расчёте плана листа. Сбрасывается и при
// отмене/закрытии диалога любым способом (watch на showAddPlannedDialog ниже), чтобы
// следующее обычное «Добавить плановую» не подхватило чужой id и не очистило план
// категории, которую пользователь трогать не просил.
const convertFromCategoryPlanId = ref<number | null>(null)
// Флаг «эта плановая позиция заводится из КОНКРЕТНОЙ позиции закупки» (кнопка
// mdi-plus-box-outline в блоке «Не привязаны к плану», см. openCreatePlannedFromActual)
// — хранит purchase_item_id, который savePlannedItem обязан привязать к только что
// созданной плановой позиции (POST /feo-planned-items/map), иначе позиция создастся, но
// закупка так и останется висеть в «Не привязаны» до следующего ручного клика. Сбрасывается
// тем же watch(showAddPlannedDialog), что и convertFromCategoryPlanId — по той же причине
// (не «протекать» в следующее открытие диалога другим путём).
const createPlannedFromActualId = ref<number | null>(null)
const plannedItemForm = ref({
  name: '',
  quantity: null as number | null,
  unit: '',
  // Плановая стоимость за единицу, ₽ (владелец, 2026-09-01) — UI-поле, подставляется
  // из каталога при выборе товара (см. onPlannedItemProductPick), полностью
  // редактируемо. С 2026-09-02 FeoPlannedItem.unit_price — реальное поле бэкенда
  // (backend/app/models/feo_planned_item.py), savePlannedItem шлёт его в POST явно;
  // пока задан и не равен 0, им ещё и пересчитывается amount (см. watch ниже).
  unitPrice: null as number | null,
  amount: null as number | null,
  payment_mode: 'one_time' as 'one_time' | 'monthly',
  planned_date: '' as string,
  monthly_start_date: '' as string,
  months_count: null as number | null,
  monthly_amount: null as number | null,
  // Происхождение (владелец, 2026-09-01) — ДВЕ НЕЗАВИСИМЫЕ галочки, см. чекбоксы
  // диалога выше. Дефолт «внутренний план» — по правилу бэкфилла (см. миграцию
  // aa1b2c3d4e5f_feo_planned_item_origin.py): позиция, заводимая человеком через
  // этот диалог, по умолчанию не является жёсткой построчной разбивкой ФЭО, пока
  // человек явно не отметит обратное.
  is_feo_breakdown: false,
  is_internal_plan: true,
})
// Владелец (2026-08-31): «Добавить плановую позицию» — подсказки/картинка из
// каталога товаров через InlineProductMatch, но FeoPlannedItem (backend модель)
// НЕ имеет product_id — это чисто UI-состояние диалога, ничего из этого не
// уходит в POST /feo-planned-items/ (см. savePlannedItem ниже, шлёт только
// name/quantity/unit/amount/...). Сбрасывается везде, где сбрасывается
// plannedItemForm (openAddPlannedItem/openConvertManualPlanToItem/
// openCreatePlannedFromActual) и при закрытии диалога любым способом.
const addPlannedProductId = ref<number | null>(null)
const addPlannedProductPhoto = ref<string | null>(null)
const addPlannedMatchConfirmed = ref<boolean | undefined>(undefined)
// Происхождение цены товара, подставленной при выборе из каталога (владелец,
// 2026-09-01: «указывать информацию по дате стоимости за единицу — как при
// формировании заявки, чтобы человек мог понять, насколько он адекватно
// планирует»). MatchCandidate (POST /products/match) уже отдаёт эти поля —
// см. useItemMatching.ts/backend/app/routers/products.py — читаем их отсюда
// напрямую, БЕЗ импорта usePriceFreshness.ts/PriceFreshnessStamp.vue (эти два
// файла ещё не в репозитории, параллельная незакоммиченная работа — импорт
// уронит сборку на проде, см. правила задачи). Подпись строим сами, ниже.
const addPlannedPriceMeta = ref<{
  price_updated_at: string | null
  price_source: string | null
  price_source_ref: string | null
} | null>(null)

// Русские подписи источника цены — минимальная копия PRICE_SOURCE_LABELS
// (usePriceFreshness.ts), намеренно НЕ импортированная (см. коммент выше у
// addPlannedPriceMeta). Держать в синхроне вручную, если появятся новые источники.
const PLANNED_PRICE_SOURCE_LABELS: Record<string, string> = {
  contract: 'договор',
  kp: 'КП',
  manual: 'вручную',
  import: 'импорт',
  monitoring: 'мониторинг цен',
}

function formatRuDateShort(iso: string | null | undefined): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (isNaN(d.getTime())) return null
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

// Подпись под полем «Плановая стоимость за единицу» — честно говорит, откуда цена
// и когда актуализирована, либо что данных нет (требование владельца, п.4).
const addPlannedPriceCaption = computed<string | null>(() => {
  if (addPlannedProductId.value == null) return null
  if (plannedItemForm.value.unitPrice == null) {
    return 'У товара в каталоге не указана цена — введите стоимость за единицу вручную.'
  }
  const meta = addPlannedPriceMeta.value
  const dateStr = meta ? formatRuDateShort(meta.price_updated_at) : null
  const parts: string[] = [dateStr ? `цена из каталога от ${dateStr}` : 'цена из каталога, дата актуализации не указана']
  const sourceLabel = meta?.price_source ? (PLANNED_PRICE_SOURCE_LABELS[meta.price_source] || meta.price_source) : null
  if (sourceLabel) {
    parts.push(`источник: ${sourceLabel}${meta?.price_source_ref ? ` · ${meta.price_source_ref}` : ''}`)
  } else {
    parts.push('источник не указан')
  }
  return parts.join(', ')
})

// Плановая сумма считается автоматически, пока стоимость за единицу задана и не
// равна 0 (требование владельца, п.3); количество по умолчанию 1, если поле пусто —
// «добавляется плановая позиция по одной штуке».
const plannedItemAmountIsComputed = computed(() => {
  const p = plannedItemForm.value.unitPrice
  return p != null && Number(p) !== 0
})

function recalcPlannedAmountFromUnitPrice() {
  if (!plannedItemAmountIsComputed.value) return
  const price = Number(plannedItemForm.value.unitPrice)
  const qtyRaw = plannedItemForm.value.quantity
  const qty = qtyRaw != null && Number(qtyRaw) > 0 ? Number(qtyRaw) : 1
  plannedItemForm.value.amount = Math.round(qty * price * 100) / 100
}

watch(
  [() => plannedItemForm.value.quantity, () => plannedItemForm.value.unitPrice],
  () => recalcPlannedAmountFromUnitPrice(),
)

// Диалог showAddPlannedDialog закрывается разными путями (Отмена/backdrop/Esc, не
// только через savePlannedItem) — сбрасываем convertFromCategoryPlanId/createPlannedFromActualId
// при ЛЮБОМ закрытии, чтобы флаги не «протекли» в следующее открытие обычной кнопкой.
// Заодно сбрасываем UI-состояние подбора по каталогу (addPlannedProductId и т.п.) —
// та же причина, оно тоже не должно «протечь» в следующее открытие.
watch(showAddPlannedDialog, (val) => {
  if (!val) {
    convertFromCategoryPlanId.value = null
    createPlannedFromActualId.value = null
    addPlannedProductId.value = null
    addPlannedProductPhoto.value = null
    addPlannedMatchConfirmed.value = undefined
    addPlannedPriceMeta.value = null
  }
})

type AddDialogCtx = Pick<SubsidyDetailContext,
  'selectedId' | 'feoCategories' | 'loadFeo' | 'refreshComparison' | 'refreshReqData' | 'factForPlanned'>

export function useFeoPlannedItemAddDialog(ctx?: AddDialogCtx) {
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success') {
    toast.addToast(text, color)
  }

  function openAddPlannedItem(categoryId: number) {
    addPlannedCategoryId.value = categoryId
    convertFromCategoryPlanId.value = null
    createPlannedFromActualId.value = null
    plannedItemForm.value = {
      // Владелец (2026-09-01): «добавляется плановая позиция по одной штуке» —
      // количество по умолчанию 1, а не пусто.
      name: '', quantity: 1, unit: '', unitPrice: null, amount: null,
      payment_mode: 'one_time', planned_date: '', monthly_start_date: '',
      months_count: null, monthly_amount: null,
      is_feo_breakdown: false, is_internal_plan: true,
    }
    addPlannedProductId.value = null
    addPlannedProductPhoto.value = null
    addPlannedMatchConfirmed.value = undefined
    addPlannedPriceMeta.value = null
    showAddPlannedDialog.value = true
  }

  // «Завести плановую позицию» — задача владельца (2026-08-09, пункт 3): у категории
  // с ручным планом (нет ни одной реальной FeoPlannedItem, план задан прямо на
  // листе node.planned_quantity/planned_amount) строка называется именем категории
  // вместо именованного товара («Great Wall POER» ожидалось увидеть, а видно имя
  // категории). Действие создаёт именованную FeoPlannedItem с тем же кол-вом/ценой,
  // что уже показаны в ручном плане листа — node.planned_quantity/planned_amount
  // САМИ НЕ МЕНЯЮТСЯ, а backend/app/services/feo_plan.py::_visit продолжает считать
  // «Плановую сумму» шапки категории ИЗ ЭТИХ ПОЛЕЙ (qty×amt), а не суммой
  // FeoPlannedItem, пока это произведение > 0 — сумма НЕ задваивается. На фронте
  // синтетическая строка (displayPlannedRowsFor) после создания реальной
  // FeoPlannedItem перестаёт отрисовываться сама (real.length > 0), так что и
  // панель не задваивает план. Дедуп по точному совпадению нормализованного имени —
  // на бэкенде (POST /feo-planned-items/, см. докстринг create_planned_item).
  // Имя предзаполняется из единственного привязанного факта, если он ровно один
  // (обычный случай — «ручной план» листа обычно закрыт одной закупкой), иначе из
  // названия категории — пользователь правит перед сохранением. Переиспользует
  // диалог showAddPlannedDialog/plannedItemForm/savePlannedItem — второй диалог не
  // пишем.
  function openConvertManualPlanToItem(node: FeoNode) {
    const facts = ctx?.factForPlanned(node.id, -node.id) ?? []
    const prefillName = facts.length === 1 ? facts[0]!.item_name : node.name
    const qty = node.planned_quantity != null ? Number(node.planned_quantity) : null
    const unitPrice = node.planned_amount != null ? Number(node.planned_amount) : null
    const amount = (qty != null && qty > 0 && unitPrice != null && unitPrice > 0) ? qty * unitPrice : null
    addPlannedCategoryId.value = node.id
    convertFromCategoryPlanId.value = node.id
    plannedItemForm.value = {
      name: prefillName,
      quantity: qty,
      unit: node.unit || '',
      unitPrice,
      amount,
      payment_mode: 'one_time',
      planned_date: '', monthly_start_date: '', months_count: null, monthly_amount: null,
      // Ручной план ФЭО (planned_quantity/planned_amount на самой категории) по
      // определению без построчной ФЭО-разбивки — та же строка панели уже
      // подписана «подробного деления в ФЭО не было» (см. шаблон выше).
      is_feo_breakdown: false, is_internal_plan: true,
    }
    addPlannedProductId.value = null
    addPlannedProductPhoto.value = null
    addPlannedMatchConfirmed.value = undefined
    addPlannedPriceMeta.value = null
    showAddPlannedDialog.value = true
  }

  // Действие владельца 2026-08-17 (жалоба «где превышение 80 318? где увидеть?»): у
  // позиции без ДЕЙСТВУЮЩЕЙ плановой привязки (обычная «не привязана» ИЛИ мёртвая ссылка
  // на удалённую плановую позицию) предлагаем сразу завести плановую позицию по данным
  // САМОЙ закупки (наименование/количество/сумма — leftGroupInfo, тот же источник, что
  // уже рисует эту строку в таблице дерева) и сразу привязать. Переиспользует
  // showAddPlannedDialog/plannedItemForm/savePlannedItem — второй диалог не пишем;
  // savePlannedItem довязывает созданную позицию к purchase_item_id по
  // createPlannedFromActualId (см. ниже).
  function openCreatePlannedFromActual(node: FeoNode, actual: FeoActualItem) {
    const info = leftGroupInfo(actual)
    addPlannedCategoryId.value = node.id
    convertFromCategoryPlanId.value = null
    createPlannedFromActualId.value = actual.purchase_item_id
    plannedItemForm.value = {
      name: info.name || actual.item_name,
      quantity: info.quantity,
      unit: info.unit || '',
      unitPrice: info.unitPrice ?? null,
      amount: info.total ?? Number(actual.fact_amount ?? actual.total_price ?? 0),
      payment_mode: 'one_time',
      planned_date: '', monthly_start_date: '', months_count: null, monthly_amount: null,
      // Заводится по факту закупки/заявки, без плана — та же семантика, что и
      // auto_created в plan_autoassign.py (см. is_internal_plan там).
      is_feo_breakdown: false, is_internal_plan: true,
    }
    addPlannedProductId.value = null
    addPlannedProductPhoto.value = null
    addPlannedMatchConfirmed.value = undefined
    addPlannedPriceMeta.value = null
    showAddPlannedDialog.value = true
  }

  // Единица измерения + цена/дата/источник товара каталога — ОДНИМ запросом
  // (GET /feo-planned-items/product-hint, добавлен рядом с этим диалогом — см.
  // докстринг эндпоинта). Координатор (2026-09-01) поймал зависимость от чужой
  // незакоммиченной работы: candidate.price_updated_at/price_source/price_source_ref
  // (MatchCandidate из POST /products/match) существуют только в РАБОЧЕМ ДЕРЕВЕ
  // параллельной сессии — в закоммиченном backend/app/routers/products.py (который
  // мы не трогаем) этих полей нет, и на проде подпись о цене всегда молчала бы.
  // product-hint читает price/price_updated_at/price_source/price_source_ref
  // напрямую из МОДЕЛИ Product — эти колонки уже закоммичены (app/models/product.py:
  // 25,40-42) — и потому не зависит от чужого незакоммиченного кода. Это ОСНОВНОЙ
  // источник цены/даты/источника; candidate.* (см. onPlannedItemProductPick) —
  // только запасной вариант на время, пока этот запрос не ответил/если он упал.
  // Гвард по product_id — пока запрос летал, пользователь мог выбрать другой товар.
  async function applyPlannedProductHint(productId: number) {
    try {
      const res = await apiFetch<{
        unit: string | null
        price: number | null
        price_updated_at: string | null
        price_source: string | null
        price_source_ref: string | null
      }>(`/feo-planned-items/product-hint?product_id=${productId}`)
      if (addPlannedProductId.value !== productId) return
      if (res?.unit) plannedItemForm.value.unit = res.unit
      if (res && res.price != null) {
        plannedItemForm.value.unitPrice = Number(res.price)
      }
      addPlannedPriceMeta.value = {
        price_updated_at: res?.price_updated_at ?? null,
        price_source: res?.price_source ?? null,
        price_source_ref: res?.price_source_ref ?? null,
      }
      recalcPlannedAmountFromUnitPrice()
    } catch {
      // Запрос не удался — остаётся то, что уже подставлено из candidate (запасной
      // вариант, см. onPlannedItemProductPick), поля остаются редактируемыми.
    }
  }

  // InlineProductMatch @pick — пользователь выбрал кандидата из каталога. Имя —
  // сразу из кандидата; единица/цена/дата/источник — предзаполняются из
  // candidate как ЗАПАСНОЙ вариант (может не содержать price_updated_at/
  // price_source на проде, см. applyPlannedProductHint выше), а затем
  // перезаписываются авторитетным ответом product-hint. Оба поля (единица,
  // стоимость за единицу) остаются полностью редактируемыми. Перезаписываем
  // unitPrice/name/фото при КАЖДОМ выборе (не только если поле было пусто) —
  // это осознанный выбор другого товара, а не первичное предзаполнение.
  function onPlannedItemProductPick(c: MatchCandidate) {
    plannedItemForm.value.name = c.name || plannedItemForm.value.name
    addPlannedProductId.value = c.product_id
    addPlannedProductPhoto.value = c.photo_url ?? null
    addPlannedMatchConfirmed.value = true
    const price = c.contract_price ?? c.price
    plannedItemForm.value.unitPrice = price != null ? Number(price) : null
    addPlannedPriceMeta.value = {
      price_updated_at: c.price_updated_at ?? null,
      price_source: c.price_source ?? null,
      price_source_ref: c.price_source_ref ?? null,
    }
    recalcPlannedAmountFromUnitPrice()
    void applyPlannedProductHint(c.product_id)
  }

  function onPlannedItemProductClear() {
    addPlannedProductId.value = null
    addPlannedProductPhoto.value = null
    addPlannedMatchConfirmed.value = undefined
    addPlannedPriceMeta.value = null
    plannedItemForm.value.name = ''
    plannedItemForm.value.unitPrice = null
  }

  // Чистит planned_quantity/planned_amount категории после переноса ручного плана в
  // именованную плановую позицию (см. openConvertManualPlanToItem/savePlannedItem выше).
  // PUT с ПОЛНЫМ payload — как в saveEditCategoryPlan: неполный payload (см. историю
  // startInlineAmt/startInlineQty в SubsidiesView.vue) обнуляет на сервере поля, которых
  // в нём нет.
  async function clearCategoryManualPlan(categoryId: number) {
    if (!ctx) return
    const cat = ctx.feoCategories.value.find(c => c.id === categoryId)
    if (cat) {
      try {
        await apiFetch(`/feo-categories/${categoryId}`, {
          method: 'PUT',
          body: JSON.stringify({
            subsidy_id: cat.subsidy_id, name: cat.name, code: cat.code ?? null, appendix: cat.appendix ?? null,
            is_active: cat.is_active, budget: cat.budget ?? null,
            feo_quantity: cat.feo_quantity ?? null, feo_unit: cat.feo_unit ?? null, feo_amount: cat.feo_amount ?? null,
            description: cat.description ?? null, unit: cat.unit ?? null,
            planned_quantity: null, planned_amount: null,
          }),
        })
        cat.planned_quantity = null
        cat.planned_amount = null
      } catch (e: any) {
        // Позиция УЖЕ создана — не откатываем и не пугаем «ошибка добавления», честно
        // говорим, что не подчистилось старое поле, и ниже всё равно перезагружаем
        // данные, чтобы пользователь видел реальное состояние, а не выдуманное.
        showSnack(e?.payload?.message || e?.detail || 'Позиция создана, но не удалось очистить старый план категории — проверьте вручную', 'error')
      }
    }
    if (ctx.selectedId.value) await ctx.loadFeo(ctx.selectedId.value)
  }

  async function savePlannedItem() {
    if (!addPlannedCategoryId.value || !plannedItemForm.value.name.trim() || !ctx) return
    savingPlannedItem.value = true
    try {
      const f = plannedItemForm.value
      const isMonthly = f.payment_mode === 'monthly'
      // Владелец (2026-09-01): «добавляется плановая позиция по одной штуке» — если
      // количество осталось пустым (в т.ч. стёрто вручную), по умолчанию 1.
      const qtyOrDefault = (f.quantity == null || (f.quantity as unknown as string) === '') ? 1 : f.quantity
      const created = await apiFetch<FeoPlannedItem>('/feo-planned-items/', {
        method: 'POST',
        body: JSON.stringify({
          feo_category_id: addPlannedCategoryId.value,
          name: f.name.trim(),
          quantity: qtyOrDefault,
          unit: f.unit || null,
          amount: isMonthly ? null : numOrNull(f.amount),
          // Цена за единицу (правка 2026-09-03) — раньше здесь не отправлялась
          // вовсе, введённая в поле «Плановая стоимость за единицу» цена молча
          // терялась (амаунт уже посчитан watch'ем из неё, а сама цена — нет).
          // См. FeoPlannedItem.unit_price / assert_tz_not_over_plan.
          // numOrNull (не `f.unitPrice ?? null` — правка 2026-09-04, жалоба
          // владельца «да какого хуя тут ожидается число, может быть пусто, может быть 0»):
          // `??` пустую строку от v-model.number НЕ ловит, только null/undefined —
          // очищенное поле уходило на сервер как '' и валило 422. См. numOrNull
          // в @/utils/numberFormat.ts.
          unit_price: isMonthly ? null : numOrNull(f.unitPrice),
          is_active: true,
          payment_mode: f.payment_mode,
          planned_date: !isMonthly && f.planned_date ? f.planned_date : null,
          monthly_start_date: isMonthly && f.monthly_start_date ? f.monthly_start_date : null,
          months_count: isMonthly ? numOrNull(f.months_count) : null,
          monthly_amount: isMonthly ? numOrNull(f.monthly_amount) : null,
          is_feo_breakdown: f.is_feo_breakdown,
          is_internal_plan: f.is_internal_plan,
        }),
      })
      // Если позиция заводилась ИЗ конкретной закупки (openCreatePlannedFromActual выше) —
      // сразу привязываем её к только что созданной плановой позиции тем же эндпоинтом, что
      // и ручное «Сопоставить с плановой» (applyMapping/POST /feo-planned-items/map), иначе
      // плановая позиция создастся, а закупка так и провисит в «Не привязаны» до следующего
      // ручного клика — половинчатое действие. Ошибку не глотаем — распаковываем
      // e.payload.message (правило проекта), позиция при этом уже создана, поэтому диалог
      // не блокируем повторной попыткой, просто честно сообщаем, что довязать не вышло.
      if (createPlannedFromActualId.value != null) {
        try {
          await apiFetch(`/feo-planned-items/map?purchase_item_id=${createPlannedFromActualId.value}&planned_item_id=${created.id}`, {
            method: 'POST',
          })
        } catch (e: any) {
          showSnack(e?.payload?.message || e?.detail || e?.message || 'Плановая позиция создана, но не удалось привязать к ней закупку — сопоставьте вручную кнопкой «Сопоставить с плановой»', 'error')
        }
        createPlannedFromActualId.value = null
      }
      // Позиция создана. Если это было действие «Перенести в плановую позицию»
      // (convertFromCategoryPlanId стоит на id этой же категории) — очищаем
      // planned_quantity/planned_amount категории: иначе они и дальше заслоняют
      // только что созданную запись при расчёте плана листа (backend суммирует
      // плановые позиции, ТОЛЬКО когда qty×amt категории не заданы), и правка
      // записи не будет менять сумму в шапке — ровно та жалоба, из-за которой
      // всё это переделывается. Сначала — успешное создание позиции (уже
      // произошло выше), потом — очистка полей категории.
      const convertCategoryId = convertFromCategoryPlanId.value === addPlannedCategoryId.value
        ? convertFromCategoryPlanId.value
        : null
      showAddPlannedDialog.value = false
      convertFromCategoryPlanId.value = null
      // refreshComparison обновляет только состав панели «План vs факт»; числа узла/
      // родителей в шапке дерева и плашка превышения читаются из planTreeByCat —
      // его обновляет refreshReqData (см. разбор жалобы владельца у deletePlannedItem
      // и уже работающий movePlannedItemToCategory). Без него новая плановая позиция
      // не давала вклад в «Плановую сумму» до перезагрузки страницы.
      await Promise.all([ctx.refreshComparison(addPlannedCategoryId.value), ctx.refreshReqData()])
      if (convertCategoryId) await clearCategoryManualPlan(convertCategoryId)
    } catch (e: any) {
      // Жалоба владельца (сессия 2026-08-19): create_planned_item теперь отдаёт 409
      // planned_item_duplicate_name вместо тихого слияния с существующей позицией (см.
      // backend/app/routers/feo_planned_items.py). Полноценный диалог выбора (привязать/
      // создать отдельную), как в FeoPlannedItemsSelect.vue, здесь не заводим — этот путь
      // создания «из закупки»/«из ручного плана категории» — редкий сценарий, здесь просто
      // честно показываем сообщение сервера, не глотаем ошибку generic-снэкбаром.
      const det = e?.payload?.details
      if (e?.status === 409 && det?.error_code === 'planned_item_duplicate_name') {
        showSnack(det.message || e.message || 'Такая плановая позиция уже есть в категории', 'error')
      } else {
        showSnack(e?.payload?.message || e?.detail || e?.message || 'Не удалось создать плановую позицию', 'error')
      }
    } finally {
      savingPlannedItem.value = false
    }
  }

  return {
    showAddPlannedDialog, addPlannedCategoryId, savingPlannedItem, plannedItemForm,
    addPlannedProductId, addPlannedProductPhoto, addPlannedMatchConfirmed, addPlannedPriceCaption,
    plannedItemAmountIsComputed, onPlannedItemProductPick, onPlannedItemProductClear,
    openAddPlannedItem, openConvertManualPlanToItem, openCreatePlannedFromActual, savePlannedItem,
  }
}
