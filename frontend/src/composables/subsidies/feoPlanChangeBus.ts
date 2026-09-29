// Общая шина «плановые данные категории изменились» — единственный сигнал
// (Правило №6, второй сигнал не заводим), на который подписываются модули,
// кэширующие СВОЙ срез плана отдельно от comparisonData (сейчас — только
// usePlanToRequest.ts::feoResiduals, признак «закуплено полностью» на дереве).
// useFeoLevel5.ts зовёт notifyFeoPlanChanged() из refreshComparison(categoryId) —
// она уже единственная точка, которую вызывают ВСЕ места сохранения/создания/
// удаления/переноса плановой позиции (edit-диалог, add-диалог, delete, drag&drop,
// undo/redo — см. грep по refreshComparison в composables/subsidies), поэтому
// вызывать notify из каждого места мутации по отдельности не нужно.
//
// Отдельный файл (не внутри useFeoLevel5.ts) специально: usePlanToRequest.ts
// уже импортирует useFeoLevel5Api из useFeoLevel5.ts, поэтому обратный импорт
// оттуда в usePlanToRequest.ts дал бы цикл — эта шина без импортов из обоих,
// разрывает цикл.
type Listener = () => void
const listeners = new Set<Listener>()

export function onFeoPlanChanged(cb: Listener): () => void {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

export function notifyFeoPlanChanged() {
  for (const cb of listeners) cb()
}
