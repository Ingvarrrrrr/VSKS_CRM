// kanbanTypes.ts — общая форма состояния колонки для ОБЩЕГО канбан-компонента
// (CategoryKanbanBoard.vue), которым пользуются и распределение заявки
// (WishDistributionKanban.vue), и разбиение закупки (PurchaseSplitKanban.vue).
// ПРАВИЛО №6: один тип колонки на оба канбана, не по копии на файл.
export interface KanbanColumnState {
  key: string
  label: string
  items: any[]
  /** Открыто поле переименования (инпут вместо текста) */
  editing?: boolean
  /** Колонка создана пользователем через «+ Столбец», а не выведена из
   *  категорий позиций — если из неё утащат последнюю позицию, колонка исчезнет
   *  без следа при следующей пересборке (используется для предупреждения при
   *  закрытии диалога, см. CategoryKanbanBoard.vue::getVanishingManualColumns). */
  manual?: boolean
  /** WishPurchasesKanban.vue (перенос позиций между уже созданными закупками
   *  заявки): колонка readonly НЕЗАВИСИМО от общего readonly-пропа доски —
   *  в неё и из неё нельзя тащить (закупка «заморожена», работа с поставщиком
   *  уже идёт). См. CategoryKanbanBoard.vue — per-column group pull/put. */
  frozen?: boolean
  /** Чип статуса рядом с заголовком колонки (WishPurchasesKanban.vue — статус
   *  закупки). Необязательное поле — остальные потребители доски его не задают. */
  statusLabel?: string
  statusColor?: string
}
