// Общий офскрин-рендер "документного" фона (бледно-серый текст договора) —
// один на все игры окна ожидания (утки, кирпичики, танчики, яйца), чтобы
// фон не дублировался (Правило №6: один источник для одного визуального эффекта).

export const DOC_BG_FONT_FAMILY = 'Consolas, "JetBrains Mono", "Courier New", monospace'

/**
 * Строит офскрин-canvas с бледно-серым текстом "договора" — вызывается один раз
 * на resize, результат кэшируется вызывающей стороной и просто копируется
 * (ctx.drawImage) в каждом кадре рендера.
 */
export function buildDocumentBackground(width: number, height: number, dpr: number): HTMLCanvasElement {
  const off = document.createElement('canvas')
  const w = Math.max(1, width)
  const h = Math.max(1, height)
  off.width = Math.max(1, Math.round(w * dpr))
  off.height = Math.max(1, Math.round(h * dpr))
  const c = off.getContext('2d')
  if (!c) return off
  c.setTransform(dpr, 0, 0, dpr, 0, 0)
  c.clearRect(0, 0, w, h)
  c.fillStyle = '#ffffff'
  c.fillRect(0, 0, w, h)

  const mono = DOC_BG_FONT_FAMILY
  const marginX = Math.max(26, w * 0.07)
  let y = 34

  c.textAlign = 'center'
  c.fillStyle = '#cfcfcf'
  c.font = `700 15px ${mono}`
  c.fillText('ДОГОВОР ПОСТАВКИ № 17/2026', w / 2, y); y += 18
  c.font = `12px ${mono}`
  c.fillText('г. Москва', w / 2, y); y += 26

  const paragraphs = [
    '1.1. Поставщик обязуется передать в собственность Покупателя товар',
    'в количестве и ассортименте согласно Спецификации, а Покупатель',
    'обязуется принять и оплатить товар на условиях настоящего Договора.',
    '1.2. Качество товара должно соответствовать требованиям, обычно',
    'предъявляемым к товарам такого рода, и подтверждается сертификатом.',
    '2.1. Цена товара устанавливается в рублях и включает НДС, расходы',
    'на упаковку, маркировку и доставку до склада Покупателя.',
    '2.2. Оплата производится в безналичном порядке в течение 10',
    'рабочих дней с момента подписания товарной накладной.',
    '3.1. Срок поставки — не позднее 30 календарных дней с даты',
    'подписания настоящего Договора обеими Сторонами.',
    '3.2. Приёмка товара по количеству и качеству производится',
    'представителем Покупателя в месте поставки с составлением акта.',
    '4.1. За нарушение сроков поставки Поставщик уплачивает пеню',
    'в размере 0,1% от стоимости недопоставленного товара за день.',
  ]
  c.textAlign = 'left'
  c.font = `11px ${mono}`
  c.fillStyle = '#dddddd'
  const lineH = 15.5
  const colW = w - marginX * 2
  const approxCharsPerLine = Math.max(10, Math.floor(colW / 6.6))
  outer:
  for (const para of paragraphs) {
    const words = para.split(' ')
    let line = ''
    for (const word of words) {
      const test = line ? line + ' ' + word : word
      if (test.length > approxCharsPerLine && line) {
        c.fillText(line, marginX, y); y += lineH
        if (y > h - 90) break outer
        line = word
      } else {
        line = test
      }
    }
    if (line) { c.fillText(line, marginX, y); y += lineH }
    y += lineH * 0.35
    if (y > h - 90) break
  }

  if (y < h - 70) {
    const tableY = y + 6
    const tableW = colW
    const tableH = 46
    const cols = 4
    c.strokeStyle = '#d9d9d9'
    c.lineWidth = 1
    c.beginPath()
    c.rect(marginX, tableY, tableW, tableH)
    for (let i = 1; i < cols; i++) {
      const lx = marginX + (tableW / cols) * i
      c.moveTo(lx, tableY); c.lineTo(lx, tableY + tableH)
    }
    c.moveTo(marginX, tableY + tableH / 2); c.lineTo(marginX + tableW, tableY + tableH / 2)
    c.stroke()
    c.font = `10px ${mono}`
    c.textAlign = 'center'
    const heads = ['№ п/п', 'Кол-во', 'Цена, руб.', 'Сумма, руб.']
    const rows2 = ['1', '120', '540,00', '64 800,00']
    for (let i = 0; i < cols; i++) {
      const cx = marginX + (tableW / cols) * (i + 0.5)
      c.fillText(heads[i] ?? '', cx, tableY + tableH / 4 + 3)
      c.fillText(rows2[i] ?? '', cx, tableY + tableH * 0.75 + 3)
    }
  }

  c.textAlign = 'left'
  c.font = `11px ${mono}`
  c.fillStyle = '#d4d4d4'
  c.fillText('______________________ / Иванов И.И.', marginX, h - 64)
  c.font = `10px ${mono}`
  c.fillText('Поставщик', marginX, h - 50)
  c.textAlign = 'right'
  c.fillText('Покупатель', w - marginX, h - 50)

  return off
}
