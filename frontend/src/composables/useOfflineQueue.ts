/**
 * Универсальная офлайн-очередь на IndexedDB (2026-09, отслеживание местоположения).
 *
 * Зачем отдельным модулем: в проекте до этой задачи не было готовой обвязки
 * "копить данные локально, пока нет сети, и досылать пакетом при восстановлении
 * связи" (см. Lessons: «Sandbox проксирует TCP», «Diff-sync needs loaded guard» —
 * похожие темы есть, но именно офлайн-очереди на IndexedDB не было). Раз для
 * геолокации это ключевое требование (спасатель может уехать туда, где нет
 * сети, и после возвращения маршрут не должен пропасть), обвязка сделана
 * достаточно универсальной, чтобы её могли переиспользовать будущие офлайн-
 * функции (чек-лист/инцидент водителя и т.п.), а не плодить второй такой же
 * механизм — см. правило проекта «переиспользовать, не дублировать».
 *
 * localStorage не подошёл бы: лимит ~5MB общий на весь домен и синхронный API
 * (блокирует поток при частом чтении/записи) — для точек геолокации, которые
 * могут копиться часами без связи, IndexedDB безопаснее и не блокирует UI.
 */

const DB_NAME = 'gala_offline_queue'
const DB_VERSION = 1

// Список object store'ов создаётся один раз при апгрейде схемы. Новая офлайн-
// функция добавляет сюда своё имя + поднимает DB_VERSION.
const STORE_NAMES = ['staff_location_points'] as const
export type QueueStoreName = (typeof STORE_NAMES)[number]

let dbPromise: Promise<IDBDatabase> | null = null

function openDb(): Promise<IDBDatabase> {
  if (!('indexedDB' in window)) {
    return Promise.reject(new Error('IndexedDB недоступен в этом браузере — офлайн-очередь не работает'))
  }
  if (dbPromise) return dbPromise
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      for (const name of STORE_NAMES) {
        if (!db.objectStoreNames.contains(name)) {
          db.createObjectStore(name, { keyPath: 'id', autoIncrement: true })
        }
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => {
      dbPromise = null
      reject(req.error || new Error('Не удалось открыть IndexedDB'))
    }
  })
  return dbPromise
}

/** Добавить один элемент в очередь. id присваивается автоматически. */
export async function enqueue<T extends object>(store: QueueStoreName, item: T): Promise<void> {
  const db = await openDb()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(store, 'readwrite')
    tx.objectStore(store).add(item as any)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

/** Все элементы очереди (с их автоприсвоенным id — нужен для последующего удаления). */
export async function getAllQueued<T>(store: QueueStoreName): Promise<Array<T & { id: number }>> {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, 'readonly')
    const req = tx.objectStore(store).getAll()
    req.onsuccess = () => resolve(req.result as Array<T & { id: number }>)
    req.onerror = () => reject(req.error)
  })
}

/** Удалить успешно отправленные элементы по их id. */
export async function removeQueued(store: QueueStoreName, ids: number[]): Promise<void> {
  if (!ids.length) return
  const db = await openDb()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(store, 'readwrite')
    const os = tx.objectStore(store)
    for (const id of ids) os.delete(id)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

/** Сколько элементов сейчас ждут отправки — для индикатора «в очереди N точек». */
export async function countQueued(store: QueueStoreName): Promise<number> {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, 'readonly')
    const req = tx.objectStore(store).count()
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}
