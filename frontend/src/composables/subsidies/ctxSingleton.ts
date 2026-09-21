// Общий хелпер для module-level singleton composables волны 5c дерева/списка
// субсидий (useSubsidyList/useFeoComments/useFeoLevel5/useFeoReqItems/
// useFeoTreeAmounts/useFeoTreeDnd/useFeoTreeExcess/useFeoTreePrefs/
// useFeoTreeState/useFeoTreeSearch/useKpiDrilldown) — раньше каждый из них
// (кроме тех, что вообще не принимают ctx, см. ниже) копировал один и тот же
// `let _api; if (!_api) _api = build(ctx)` (Правило №6 — не дублировать).
//
// Баг (владелец, 21.09, П2): `if (!_api)` пересобирал API ТОЛЬКО если его
// ещё ни разу не строили — весь реактивный API навсегда захватывал ctx
// ПЕРВОГО маунта SubsidiesView.vue (включая allSubsidies и прочие ref'ы
// родителя). После ухода на /orders и возврата на /subsidies компонент
// монтируется заново и строит НОВЫЙ ctx (новый `allSubsidies` ref и т.п.),
// но singleton продолжал отдавать API, закрытый над СТАРЫМ ctx — рендер
// читал старые refs, поэтому удалённая на прошлом маунте строка субсидии не
// исчезала со экрана до принудительного F5.
//
// makeCtxSingleton(build) возвращает use(ctx?):
//   - ctx передан И отличается (по ссылке) от ctx, на котором строили api в
//     прошлый раз → пересобрать через build(ctx) и запомнить новый ctx;
//   - ctx не передан (дочерний компонент типа FeoTreeRow.vue, которому нужен
//     уже готовый API без прокидывания полного ctx) → отдать уже построенный
//     api как есть;
//   - api ещё нет и ctx не передан → бросить читаемую ошибку (компонент
//     смонтировался раньше SubsidiesView.vue, которая обязана вызвать
//     use(ctx) первой в своём <script setup>).
//
// Composables БЕЗ ctx вообще (useFeoComments(), useFeoTreePrefs()) этот
// хелпер не используют — там нечему "устаревать": их состояние не читает
// refs родителя, а хранит собственное (localStorage-preferences/кэш видимости
// комментариев), которое обязано пережить размонтирование/монтирование
// SubsidiesView.vue как единое целое.
export function makeCtxSingleton<Ctx extends object, Api>(
  build: (ctx: Ctx) => Api,
  errorMessage: string,
) {
  let api: Api | null = null
  let builtCtx: Ctx | null = null

  return function use(ctx?: Ctx): Api {
    if (ctx && ctx !== builtCtx) {
      api = build(ctx)
      builtCtx = ctx
    }
    if (!api) throw new Error(errorMessage)
    return api
  }
}
