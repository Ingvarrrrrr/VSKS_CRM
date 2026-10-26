// wishFeoMissingTarget.ts — ЕДИНСТВЕННОЕ место, которое решает «какое поле
// виновато и что написать в алерте/тултипе», когда wishFeoCategoryMissing
// === true (useWishForm.ts). Раньше алерт и подсветка всегда указывали на
// data-field="feo_category" (и тот и другой безусловно), даже когда субсидия
// ещё не выбрана — в этом случае FeoTreeSelect не рендерится вовсе
// (`v-if="wishForm.subsidy_id && ..."` в WishFormDialog.vue), рамка остаётся
// пустой и узкой, стрелка от кнопки визуально утыкается в таблицу позиций
// под ней. Жалоба владельца (2026-10-26): «В какое место ведёт стрелочка,
// как человек должен понять, что делать? Если она ведёт к свёрнутому полю —
// поле должно разворачиваться».
//
// Логика выбора цели:
//  - субсидия не выбрана → подсветить сам выбор субсидии (data-field="subsidy_id"),
//    текст — «сначала выберите субсидию»;
//  - субсидия выбрана, feo_per_item выключен → цель — САМО поле выбора в шапке
//    (data-field="feo_category" → внутри него data-field="feo_category_select",
//    см. useWishForm.ts::highlightMissingFeoCategory);
//  - feo_per_item включён → цель — поле категории КОНКРЕТНОЙ строки-позиции
//    без категории (data-field="item-feo-category-select-<uid>" —
//    ItemsTableFlat.vue, feo-attrs-row под основной строкой товара; НЕ
//    item-row-<uid> целиком — тот id висит на ВЕРХНЕЙ строке с корзиной
//    удаления, координатор 2026-10-26 поймал стрелку, целящуюся в корзину).
//
// title/detail — РАЗДЕЛЬНО (координатор, 2026-10-26, повторная проверка):
// title идёт в заголовок алерта (жирным), detail — ПОЯСНЕНИЕ без повтора
// заголовка строкой ниже. tooltip — ОТДЕЛЬНОЕ короткое предложение по сути
// для тултипа кнопок (НЕ title+detail подряд — координатор поймал буквальный
// повтор). Слова «выше»/«ниже» намеренно не используются нигде в текстах —
// таблица позиций физически НИЖЕ плашки, дерево категории тоже рисуется ПОД
// текстом, так что «заполните выше»/«выберите ниже» были фактической ошибкой
// направления. Текст — ТОЛЬКО отсюда, больше нигде в проекте текст этой
// ошибки не формируется (WishFormDialog.vue подставляет title/detail, не
// дублирует сам текст).

// buttonLabel — владелец, 26.10.2026: плашка «Субсидия не выбрана...» висела
// текстом без действия. Кнопка в плашке зовёт ТОТ ЖЕ onHighlightMissingFeoCategory
// (WishFormDialog.vue — скролл/раскрытие раздела/открытие дерева категории),
// что и подсветка по клику на заблокированную кнопку отправки — второй
// механизм прокрутки/раскрытия не заводится (ПРАВИЛО №6). Текст кнопки —
// отсюда же, единственный источник текстов этой ошибки.
export type WishFeoMissingTarget =
  | { kind: 'subsidy'; title: string; detail: string; tooltip: string; buttonLabel: string }
  | { kind: 'category'; title: string; detail: string; tooltip: string; buttonLabel: string }
  | { kind: 'item'; uid: string | number; title: string; detail: string; tooltip: string; buttonLabel: string }

function build(
  kind: WishFeoMissingTarget['kind'],
  title: string,
  detail: string,
  tooltip: string,
  buttonLabel: string,
  extra?: Record<string, unknown>
): WishFeoMissingTarget {
  return { kind, title, detail, tooltip, buttonLabel, ...extra } as WishFeoMissingTarget
}

export function resolveWishFeoMissingTarget(params: {
  subsidyId: number | null | undefined
  feoPerItem: boolean
  firstMissingItem: { _uid?: string | number } | null | undefined
}): WishFeoMissingTarget {
  const { subsidyId, feoPerItem, firstMissingItem } = params

  if (!subsidyId) {
    return build(
      'subsidy',
      'Субсидия не выбрана.',
      'Выберите её в разделе «Основная информация» — после этого появится выбор категории ФЭО.',
      'Сначала выберите субсидию.',
      'Выбрать субсидию'
    )
  }

  const title = 'Конечная категория ФЭО не выбрана — отправить заявку на согласование нельзя'

  if (feoPerItem) {
    if (firstMissingItem && firstMissingItem._uid != null) {
      return build(
        'item',
        title,
        'Не у всех позиций выбрана конечная категория ФЭО — заполните её у каждой позиции в таблице (строка подсвечена).',
        'Не у всех позиций выбрана категория ФЭО.',
        'Выбрать категорию',
        { uid: firstMissingItem._uid }
      )
    }
    return build(
      'category',
      title,
      'Не у всех позиций выбрана конечная категория ФЭО — заполните её у каждой позиции в таблице.',
      'Не у всех позиций выбрана категория ФЭО.',
      'Выбрать категорию'
    )
  }

  return build(
    'category',
    title,
    'Без конечной категории закупка не попадёт ни в один план ФЭО и её сумма потеряется. Выберите категорию в дереве, углубившись до самого конечного уровня, а если категория неизвестна — нажмите «Не определена».',
    'Выберите категорию ФЭО до конечного уровня.',
    'Выбрать категорию'
  )
}
