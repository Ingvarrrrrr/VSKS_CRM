// Общая загрузка картинок-спрайтов для игр окна ожидания (один механизм на все игры).
// Спрайты — из наборов Kenney (kenney.nl), лицензия CC0, см. THIRD_PARTY_LICENSES.md.
// URL берётся через import из Vite (`import duckUrl from './sprites/duck/duck.png'`).

const cache = new Map<string, HTMLImageElement>()

/** Картинка по URL; одна на всё приложение. Пока не загрузилась — `isSpriteReady` = false. */
export function loadSprite(url: string): HTMLImageElement {
  let img = cache.get(url)
  if (!img) {
    img = new Image()
    img.decoding = 'async'
    img.src = url
    cache.set(url, img)
  }
  return img
}

export function isSpriteReady(img: HTMLImageElement): boolean {
  return img.complete && img.naturalWidth > 0
}
