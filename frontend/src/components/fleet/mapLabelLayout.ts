/**
 * 2026-09 (правка после ревью): подписи пинов на карте («Курск» / «ДНР г.
 * Донецк» / «1 ТС» и т.п.) рисуются как текст рядом с кружком пина и раньше
 * никак не проверяли, не залезают ли они на соседние подписи или на чужой
 * кружок-маркер — при тесном расположении пинов (реалистичная география:
 * Курск и Донецк действительно близко друг к другу) подписи налезали друг на
 * друга и «тонули» под чужим кружком.
 *
 * Модуль вынесен отдельно от RussiaMapSvg.vue (Правило №5 — не размазывать
 * геометрию по компоненту): чистая функция без побочных эффектов, которую
 * легко покрыть измерением через getBoundingClientRect в e2e.
 *
 * 2026-09 (правка владельца, «разброс непонятен»): раньше сторону подписи
 * (сверху/слева/справа от кружка) выбирал алгоритм — по минимальному
 * смещению, нужному, чтобы развести боксы. В итоге у трёх соседних городов
 * подпись оказывалась в трёх разных местах относительно кружка (Курск —
 * сверху, Донецк — слева, Ростов — справа), и карту было тяжело читать: не
 * с первого взгляда понятно, какая подпись к какому кружку относится.
 *
 * Новое жёсткое правило (без исключений в алгоритме раздвижки):
 *  - подпись ВСЕГДА справа от кружка, по вертикали — по центру кружка;
 *  - текст выровнен по левому краю (owner side эффективно "start"), поэтому
 *    все подписи начинаются на одинаковом расстоянии от своего кружка;
 *  - раздвижка при тесноте двигает подпись ТОЛЬКО по вертикали (вверх/вниз);
 *    прежний горизонтальный люфт (MAX_DX) убран целиком — сторона подписи
 *    не "гуляет" ради разъезда;
 *  - единственное исключение из "всегда справа" — географическое, не
 *    алгоритмическое: если подпись физически не помещается справа и вылезает
 *    за правый край карты (актуально для городов у восточной границы —
 *    Владивосток, Петропавловск-Камчатский), она переносится влево, с
 *    выравниванием по правому краю (чтобы не вылезать за рамку с другой
 *    стороны). Эта проверка делается один раз при построении подписи, не
 *    зависит от соседей и не участвует в раздвижке;
 *  - если после исчерпания вертикального запаса подписи всё равно
 *    накладываются (очень близкие города) — молча наложить их нельзя;
 *    подпись пина с МЕНЬШИМ числом машин скрывается (показывается по
 *    наведению на пин, см. .pin-label-name--hidden в RussiaMapSvg.vue).
 *
 * 2026-09 (владелец: «можно приблизить карту?») — RussiaMapSvg.vue теперь умеет
 * зумить/таскать карту через viewBox, а кружки/подписи контрмасштабируются
 * (см. .pin-zoom-counter там же), чтобы визуально не раздуваться. Это меняет
 * геометрию для этого модуля: HALO_GAP/LABEL_NAME_GAP/MAX_DY и ширина текста —
 * величины «в экранных пикселях при zoom=1»; при zoom>1 тот же ВИЗУАЛЬНЫЙ
 * размер занимает МЕНЬШЕ пространства в «сырых» координатах карты (ровно во
 * столько раз меньше, во сколько увеличен zoom). Раздвижка обязана считать
 * именно в текущих «сырых» координатах (в них же живут pin.x/pin.y) — иначе
 * при приближении расположенные далеко друг от друга (на экране) города
 * продолжали бы считаться тесными, и однажды скрытая подпись никогда не
 * вернулась бы на место, даже если после зума места стало с избытком.
 * layoutPinLabels(pins, zoom) — второй параметр опционален (по умолчанию 1,
 * поведение как раньше), передаётся из RussiaMapSvg.vue как текущий zoomLevel.
 */
import type { MapPin } from './russiaMapPins'

interface Box {
  x: number
  y: number
  w: number
  h: number
}

function boxesOverlap(a: Box, b: Box): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y
}

/** Величина пересечения по вертикали (>0, если реально пересекаются —
 * вызывать только после boxesOverlap). Раздвижка теперь работает только по
 * этой оси — горизонтальной версии (overlapAmounts.x) больше нет смысла
 * считать, сторона подписи фиксирована. */
function yOverlapAmount(a: Box, b: Box): number {
  return Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)
}

let measureCtx: CanvasRenderingContext2D | null | undefined
function measureTextWidth(text: string, weight: string, size: number, family = 'Inter, system-ui, sans-serif'): number {
  if (typeof document === 'undefined') return text.length * size * 0.58
  if (measureCtx === undefined) {
    const canvas = document.createElement('canvas')
    measureCtx = canvas.getContext('2d')
  }
  if (!measureCtx) return text.length * size * 0.58
  measureCtx.font = `${weight} ${size}px ${family}`
  return measureCtx.measureText(text).width
}

export interface LabelOffset {
  /** Вертикальный сдвиг от центра кружка (px), результат раздвижки. */
  nameDy: number
  /** Сторона кружка, с которой рисуется подпись. 'right' всегда, кроме
   * географического исключения (см. комментарий модуля выше). */
  side: 'left' | 'right'
  /** Подпись накладывается на соседнюю даже после исчерпания вертикального
   * запаса — скрыта по умолчанию, показывается по наведению на пин. */
  hidden: boolean
}

interface MovableLabel {
  id: string | number
  count: number
  side: 'left' | 'right'
  /** Абсолютная (в координатах SVG) X левого края бокса подписи — фиксирована,
   * раздвижка её не трогает (это и есть требование "сторону не менять"). */
  boxX: number
  /** Абсолютная Y центра кружка-пина — база, от которой откладывается dy. */
  cy: number
  w: number
  h: number
  dy: number
  /** false — подпись проиграла конфликт и скрыта, дальше не участвует ни в
   * раздвижке, ни в проверках столкновений для остальных подписей. */
  active: boolean
}

// 2026-09: viewBox карты в RussiaMapSvg.vue — 0 0 1171 611 (настоящая карта
// РФ владельца). Используется здесь, чтобы решить, помещается ли подпись
// справа от восточных пинов (Владивосток и т.п.), не вылезая за рамку.
// MAP_HEIGHT добавлен вместе с приближением карты (RussiaMapSvg.vue считает
// начальный/сброшенный viewBox и его границы панорамирования от обоих).
export const MAP_WIDTH = 1171
export const MAP_HEIGHT = 611
export const MAP_EDGE_MARGIN = 8 // зазор от подписи до края viewBox

// 2026-09-эксперимент (правка по замечанию владельца, см. блок "Дуговые
// подписи" ниже): было 12 — на дуговом варианте символам физически негде
// было поместиться между сплошным кружком и внешним краем ореола. Поднято до
// 16, чтобы дуга внутри ореола вмещала читаемый текст. Безопасно для ВСЕХ
// пинов (declutterPins в FleetRegionsView.vue меряет минимальную дистанцию
// между центрами именно от этой константы — раздвижка сама подстроится под
// новое значение, ореолы разных кружков по-прежнему не смогут наложиться друг
// на друга).
export const HALO_GAP = 16        // радиус ореола = pin.radius + HALO_GAP
// 2026-09 (доделка по правке владельца): подпись была крупной (font-size 21)
// и висела заметно выше кружка (GAP=20) — на глаз читалась как "сама по
// себе", а не как принадлежащая своему пину. Кегль уменьшен вдвое.
export const LABEL_NAME_GAP = 6   // поверх (pin.radius + HALO_GAP) — минимальный зазор до текста
export const LABEL_NAME_FONT_SIZE = 11

const MARGIN = 4
const MAX_PASSES = 150
// Единственная степень свободы раздвижки теперь — вертикаль (см. комментарий
// модуля). Запас увеличен относительно старого MAX_DY=14: раньше часть
// тесноты снималась горизонтальным сдвигом (MAX_DX=46), которого больше нет.
const MAX_DY = 60

/**
 * Считает поправку для подписи «имя» (у пина): сторону (почти всегда
 * 'right'), вертикальный сдвиг для раздвижки и флаг "скрыта" для случаев,
 * когда развести подписи по вертикали не получилось (см. комментарий модуля).
 *
 * @param zoom Текущий уровень приближения карты (RussiaMapSvg.vue,
 *   MAP_WIDTH/viewBox.w) — 1 = обычный вид. HALO_GAP/LABEL_NAME_GAP/MAX_DY и
 *   ширина текста делятся на zoom: контрмасштабирование в RussiaMapSvg.vue
 *   держит их визуальный (экранный) размер постоянным, поэтому в «сырых»
 *   координатах карты, где считается раздвижка, они пропорционально мельче
 *   при большем zoom — см. комментарий модуля.
 */
export function layoutPinLabels(pins: MapPin[], zoom: number = 1): Map<string | number, LabelOffset> {
  const z = zoom > 0 ? zoom : 1
  const haloGap  = HALO_GAP / z
  const nameGap  = LABEL_NAME_GAP / z
  const maxDy    = MAX_DY / z
  const margin   = MARGIN / z
  const labelH   = 14 / z

  const markers = pins.map(p => ({
    id: p.id,
    box: { x: p.x - (p.radius + haloGap), y: p.y - (p.radius + haloGap), w: 2 * (p.radius + haloGap), h: 2 * (p.radius + haloGap) } as Box,
  }))

  const labels: MovableLabel[] = []
  for (const p of pins) {
    if (!p.name) continue
    const anchorGap = p.radius + haloGap + nameGap
    const textWidth = (measureTextWidth(p.name, '600', LABEL_NAME_FONT_SIZE) + 6) / z
    const rightEdge = p.x + anchorGap + textWidth
    // Географическое исключение из "всегда справа" — см. комментарий модуля.
    // Проверяется один раз по факту помещения в карту, не зависит от соседей.
    // MAP_WIDTH/MAP_EDGE_MARGIN — абсолютные границы карты, zoom их не меняет.
    const side: 'left' | 'right' = rightEdge <= MAP_WIDTH - MAP_EDGE_MARGIN ? 'right' : 'left'
    const boxX = side === 'right' ? p.x + anchorGap : p.x - anchorGap - textWidth
    labels.push({ id: p.id, count: p.count, side, boxX, cy: p.y, w: textWidth, h: labelH, dy: 0, active: true })
  }

  const boxOf = (l: MovableLabel): Box => ({ x: l.boxX, y: l.cy + l.dy - l.h / 2, w: l.w, h: l.h })
  const dyClamp = (v: number) => Math.max(-maxDy, Math.min(maxDy, v))

  for (let pass = 0; pass < MAX_PASSES; pass++) {
    let moved = false

    // 1) подпись vs чужой кружок-маркер (halo) — толкаем только по Y.
    for (const l of labels) {
      if (!l.active) continue
      const lb = boxOf(l)
      for (const m of markers) {
        if (m.id === l.id) continue
        if (boxesOverlap(lb, m.box)) {
          const ov = yOverlapAmount(lb, m.box)
          const dir = (l.cy + l.dy) <= (m.box.y + m.box.h / 2) ? -1 : 1
          const next = dyClamp(l.dy + dir * (ov + margin))
          if (Math.abs(next - l.dy) > 0.01) {
            l.dy = next
            moved = true
          }
        }
      }
    }

    // 2) подпись vs подпись (разных пинов) — тоже только по Y.
    for (let i = 0; i < labels.length; i++) {
      for (let j = i + 1; j < labels.length; j++) {
        const a = labels[i]
        const b = labels[j]
        if (!a.active || !b.active) continue
        const ab = boxOf(a)
        const bb = boxOf(b)
        if (boxesOverlap(ab, bb)) {
          const ov = yOverlapAmount(ab, bb)
          const push = ov / 2 + margin
          const aCy = a.cy + a.dy
          const bCy = b.cy + b.dy
          let aNext = a.dy
          let bNext = b.dy
          if (aCy <= bCy) {
            aNext = dyClamp(a.dy - push)
            bNext = dyClamp(b.dy + push)
          } else {
            aNext = dyClamp(a.dy + push)
            bNext = dyClamp(b.dy - push)
          }
          if (Math.abs(aNext - a.dy) > 0.01 || Math.abs(bNext - b.dy) > 0.01) {
            a.dy = aNext
            b.dy = bNext
            moved = true
          }
        }
      }
    }

    if (!moved) break
  }

  // 3) Что осталось пересекающимся после исчерпания вертикального запаса —
  //    молча наложить или обрезать нельзя (требование владельца). Скрываем
  //    подпись пина с МЕНЬШИМ числом машин — она показывается по наведению
  //    на пин (см. .pin-label-name--hidden в RussiaMapSvg.vue).
  for (let guard = 0; guard < labels.length + 2; guard++) {
    let hiddenSomething = false

    for (let i = 0; i < labels.length; i++) {
      for (let j = i + 1; j < labels.length; j++) {
        const a = labels[i]
        const b = labels[j]
        if (!a.active || !b.active) continue
        if (boxesOverlap(boxOf(a), boxOf(b))) {
          const loser = a.count <= b.count ? a : b
          loser.active = false
          hiddenSomething = true
        }
      }
    }
    for (const l of labels) {
      if (!l.active) continue
      for (const m of markers) {
        if (m.id === l.id) continue
        if (boxesOverlap(boxOf(l), m.box)) {
          l.active = false
          hiddenSomething = true
        }
      }
    }

    if (!hiddenSomething) break
  }

  const result = new Map<string | number, LabelOffset>()
  for (const p of pins) result.set(p.id, { nameDy: 0, side: 'right', hidden: false })
  for (const l of labels) {
    result.set(l.id, { nameDy: l.dy, side: l.side, hidden: !l.active })
  }
  return result
}

// ═══════════════════════════════════════════════════════════════════════════
// ── Дуговые подписи (эксперимент, владелец: «название по кругу вокруг
// кружка города, кегль уменьшать, чтобы в два круга не шло») ────────────────
//
// Второй, взаимоисключающий способ рисовать имя города — вдоль дуги над
// маркером вместо прямой строки сбоку. Переключение живёт в RussiaMapSvg.vue
// (LABEL_RENDER_MODE) — straight-код выше НЕ тронут и остаётся рабочим
// путём отката, если владельцу дуги не понравятся на реальных 15 городах.
//
// Геометрия дуги: строго ВЕРХНЯЯ половина окружности (9 часов → 12 → 3 часа,
// ARC_SPAN_DEG=180). Не вся окружность специально: если дать имени уходить в
// нижнюю половину, буквы там читались бы вверх ногами (SVG textPath держит
// глиф "верхом" относительно касательной к пути, а не относительно экрана —
// на нижней дуге касательная развёрнута на 180°). Ограничившись верхней
// половиной, лишаемся части длины дуги, зато гарантированно без переворота.
//
// 2026-09 (правка после замечания владельца по живой карте — меняет всю
// геометрию): первая версия рисовала дугу СНАРУЖИ ореола (halo) маркера. На
// плотной группе (Москва/Подольск/Курск — три пина в считанных пикселях друг
// от друга) кольца соседних подписей начинали пересекаться, алгоритм ужимал
// кегль или вовсе прятал/переводил на straight-fallback — итог: «Москва,
// Подольск, Курск... не видны». Владелец: дуга должна идти ВНУТРИ ореола, по
// его бледной полупрозрачной части — не там, где насыщенный цвет кружка, и
// не снаружи ореола вовсе. Из этого прямо следует:
//  - подпись целиком умещается в границах СВОЕГО ореола (радиус дуги строго
//    между pin.radius и pin.radius+HALO_GAP) — она физически не может задеть
//    чужую подпись, пока не пересекаются сами ореолы, а ореолы разных пинов
//    не пересекаются НИКОГДА (declutterPins в FleetRegionsView.vue раздвигает
//    центры именно на сумму (radius+HALO_GAP) обоих + запас — тот же HALO_GAP,
//    что и здесь, импортируется оттуда же). Значит раздвижка/сжатие между
//    РАЗНЫМИ пинами дуговым подписям на этом радиусе не нужна вовсе;
//  - кегль подбирается из ДВУХ независимых ограничений одного и того же пина:
//    (а) высота символов должна уместиться в толщину кольца ореола (не задеть
//        ни сплошной кружок изнутри, ни выйти за внешний край ореола снаружи)
//        — см. fitInnerArcLabel/BAND_ASCENT_RATIO;
//    (б) ширина имени должна уместиться в длину дуги на этом (уменьшенном по
//        сравнению с "снаружи ореола") радиусе — короче дуга ⇒ мельче шрифт
//        при том же имени.
//  - HALO_GAP (толщина кольца ореола) поднят с 12 до 16px — на 12px тексту
//    даже на ARC_FONT_MIN было физически негде поместиться между сплошным
//    кружком и внешним краем ореола (проверено измерением, см. отчёт задачи).
//    Это безопасно расширяет ореол ДЛЯ ВСЕХ пинов (используется и в
//    declutterPins, и в straight-режиме), но НЕ создаёт наложений между
//    РАЗНЫМИ кружками — declutterPins меряет минимальную дистанцию именно от
//    этой константы, поэтому раздвижка пинов автоматически подстраивается
//    под новое значение (см. комментарий в russiaMapPins/FleetRegionsView).
//
// 2026-09 (правка владельца №2, «для больших названий пускай по внешнему
// радиусу ореола»): если имя не влезает во внутреннюю дугу даже на
// ARC_FONT_MIN (длинные имена — «Петропавловск-Камчатский», «Ростов-на-Дону»),
// раньше это тушило дугу и включало straight-fallback сбоку — на карте
// получались вперемешку два разных стиля подписи. Правило выбора радиуса
// теперь ЯВНОЕ и без исключений в fallback прямую подпись (см. fitArcLabel):
//  1) считаем ВНУТРЕННЮЮ дугу (fitInnerArcLabel) — короткие имена почти
//     всегда получают на ней ARC_FONT_MAX без всяких компромиссов;
//  2) не влезло вообще (даже ARC_FONT_MIN не проходит хотя бы одно из двух
//     ограничений — высота кольца ИЛИ длина дуги) — сразу внешняя дуга;
//  3) влезло, но со сжатым кеглем (типичный случай — «Ростов-на-Дону»: 14
//     символов формально проходят порог ARC_FONT_MIN на внутренней дуге, но
//     с кеглем заметно мельче соседних ARC_FONT_MAX) — СРАВНИВАЕМ с тем, что
//     дала бы внешняя дуга на БАЗОВОМ радиусе (pin.radius+HALO_GAP+
//     ARC_OUTER_INSET, без эскалации): внешняя окружность длиннее внутренней,
//     поэтому почти всегда даёт кегль не меньше, и на именах, которым
//     внутренняя дуга тесна, выигрывает заметно. Побеждает вариант с БОЛЬШИМ
//     кеглем (см. OUTER_FONT_ADVANTAGE_THRESHOLD — порог "заметно", чтобы не
//     дёргать выбор из-за долей пикселя) — короткие имена, у которых оба
//     варианта упираются в один и тот же потолок ARC_FONT_MAX, остаются
//     внутри (ничья решается в пользу внутренней);
//  4) даже внешняя база не вписалась по длине на ARC_FONT_MIN (совсем длинное
//     имя на маленьком кружке) — увеличиваем радиус внешней дуги шагами
//     (ARC_RADIUS_STEP), пока не впишется. Циркуль растёт — длина
//     полуокружности растёт линейно с радиусом, поэтому решение всегда
//     находится за конечное число шагов (см. ARC_RADIUS_MAX_STEPS — верхняя
//     граница на случай патологически длинного имени, не должна достигаться
//     на реальных городах). Ни один шаг не обрезает и не прячет имя.
//
// Внешняя дуга — уже НЕ «внутри своего ореола», она выходит за его край и
// физически может задеть дугу/ореол СОСЕДНЕГО пина (именно это и было
// найдено на живой карте на кластерах Москва—Подольск—Курск и Донецк—Курск—
// Ростов-на-Дону — близко стоящие города). Владелец прямо запретил прятать
// подпись пина с меньшим числом машин (старая механика labelOffsets.hidden
// для straight-режима) — вместо этого:
//  - для ВНЕШНИХ дуг заведена отдельная раздвижка resolveOuterArcAngles:
//    вместо сдвига по Y (как в straight/layoutPinLabels) она двигает УГОЛ
//    начала текста вдоль ТОЙ ЖЕ дуги (SVG textPath startOffset) — имя того же
//    пина просто съезжает влево/вправо по своей полуокружности, оставаясь
//    строго в верхней половине (не переворачивается);
//  - если раздвижки по углу не хватает (оба конца дуги уже упёрлись в 9 и 3
//    часа) — конфликтующим пинам ещё увеличивается радиус (тот же шаг
//    ARC_RADIUS_STEP, что и при первичном подборе) и раздвижка по углу
//    повторяется на новом, более просторном радиусе — см. layoutArcPinLabels;
//  - внутренние дуги в этой раздвижке не участвуют вовсе (их ореолы гарантированно
//    не пересекаются, см. пункт выше) — экономит проходы и не может испортить
//    уже гарантированно бесконфликтный случай.
export const ARC_FONT_MAX = 11     // потолок кегля дуговой подписи (совпадает с LABEL_NAME_FONT_SIZE — визуально не крупнее прямой подписи)
export const ARC_FONT_MIN = 6      // нижний предел читаемости внутри узкого ореольного кольца
const ARC_SPAN_DEG = 180           // строго верхняя половина окружности (см. комментарий выше)
const ARC_FILL_RATIO = 0.88        // имя занимает не более этой доли длины дуги — небольшой зазор по краям
const ARC_BAND_INNER_INSET = 3     // отступ радиуса ВНУТРЕННЕЙ дуги от края сплошного кружка (pin.radius) — не даёт baseline сливаться со сплошной заливкой
const ARC_BAND_OUTER_MARGIN = 1    // отступ верхушек букв внутренней дуги от внешнего края ореола
// Доля кегля, на которую типичный кириллический символ (Inter/system-ui,
// 600) выступает НАРУЖУ от опорной линии дуги (baseline) — определяет,
// сколько кольца ореола реально доступно под сам текст (см. band-ограничение
// в fitInnerArcLabel). Подобрано с запасом (проверено скриншотом на реальной
// карте — буквы не вылезают за внешний край ореола и не касаются кружка).
const BAND_ASCENT_RATIO = 0.82

// ── Внешняя дуга (для имён, не влезающих во внутреннюю) ─────────────────────
const ARC_OUTER_INSET = 4          // зазор от внешнего края ореола (pin.radius+HALO_GAP) до начала внешней дуги — визуально отделяет её от ореола
const ARC_OUTER_BAND_THICKNESS = 16 // доступная толщина "кольца" под текст внешней дуги — здесь уже нет соседнего кольца, которое можно задеть, поэтому щедрее внутренней
const ARC_RADIUS_STEP = 6          // шаг увеличения радиуса внешней дуги — и при первичном подборе кегля (длинное имя не влезло), и при раздвижке конфликтующих пинов
const ARC_RADIUS_MAX_STEPS = 10    // защитный потолок числа шагов увеличения радиуса (не должен достигаться на реальных именах городов — см. комментарий модуля)
const OUTER_LABEL_GAP_PX = 3       // минимальный зазор между боксами внешних подписей/чужим ореолом после раздвижки по углу
const MAX_OUTER_PASSES = 200       // проходов раздвижки по углу на один "раунд" (до эскалации радиуса)

export interface ArcLabelResult {
  /** Радиус дуги (px, в локальных координатах пина — как HALO_GAP/LABEL_NAME_GAP,
   * используется в шаблоне НАПРЯМУЮ, без деления на zoom: pin-zoom-counter
   * группа уже контрмасштабирует всё внутри себя, см. комментарий модуля выше
   * про HALO_GAP/LABEL_NAME_GAP/MAX_DY). Для band='inner' строго между
   * pin.radius и pin.radius+HALO_GAP (по бледной части ореола); для
   * band='outer' — pin.radius+HALO_GAP+ARC_OUTER_INSET и выше (см. комментарий
   * модуля про эскалацию радиуса). */
  radius: number
  /** Подобранный кегль имени, ARC_FONT_MIN..ARC_FONT_MAX. */
  fontSize: number
  /** 'inner' — дуга внутри ореола (короткие имена, стандартный случай).
   * 'outer' — дуга по внешнему краю ореола и дальше (длинные имена, не
   * поместившиеся внутри даже на ARC_FONT_MIN) — см. комментарий модуля. */
  band: 'inner' | 'outer'
  /** SVG textPath startOffset в процентах (0..100) — позиция ЦЕНТРА текста
   * вдоль дуги (buildArcPath строит путь от 9 через 12 к 3 часам, 50% — это
   * 12 часов, верхушка). Для band='inner' всегда 50 (раздвижка не нужна —
   * ореолы разных пинов никогда не пересекаются). Для band='outer' подобран
   * коллизионным алгоритмом resolveOuterArcAngles (см. комментарий модуля):
   * имя может быть смещено влево/вправо от верхушки, чтобы не задеть дугу
   * соседнего пина, оставаясь строго в пределах верхней половины окружности. */
  startOffsetPercent: number
}

/** SVG path для <textPath> — дуга радиуса r с центром в локальном (0,0)
 * (центр кружка-пина), от 9 часов через 12 к 3 часам (ARC_SPAN_DEG=180,
 * см. комментарий модуля: строго верхняя половина, чтобы текст не
 * переворачивался). Читается слева направо без переворота на любом имени. */
export function buildArcPath(r: number): string {
  const half = ARC_SPAN_DEG / 2
  const rad = (deg: number) => (deg * Math.PI) / 180
  const x = r * Math.sin(rad(half))
  const y = -r * Math.cos(rad(half))
  const largeArc = ARC_SPAN_DEG > 180 ? 1 : 0
  // Sweep=1 (по часовой в SVG-системе с y вниз): от (-x,y) через верх (0,-r) до (x,y).
  return `M ${(-x).toFixed(2)} ${y.toFixed(2)} A ${r.toFixed(2)} ${r.toFixed(2)} 0 ${largeArc} 1 ${x.toFixed(2)} ${y.toFixed(2)}`
}

function arcLength(r: number): number {
  return (Math.PI * ARC_SPAN_DEG) / 180 * r
}

/**
 * Пробует ВНУТРЕННЮЮ дугу для одного пина, независимо от соседей (подпись
 * целиком внутри своего ореола, поэтому с соседями пересечься не может — см.
 * комментарий модуля). Два независимых ограничения кегля:
 *  (а) высота символов (≈ fontSize*BAND_ASCENT_RATIO) должна уместиться в
 *      кольцо ореола между pin.radius+ARC_BAND_INNER_INSET и pin.radius+HALO_GAP
 *      минус ARC_BAND_OUTER_MARGIN;
 *  (б) ширина имени на этом кегле должна уместиться в ARC_FILL_RATIO длины
 *      дуги радиуса r (measureTextWidth масштабируется линейно с font-size —
 *      одно измерение при ARC_FONT_MAX + масштаб вместо итеративного перемера).
 * Возвращает null, если даже ARC_FONT_MIN не проходит хотя бы одно из двух
 * ограничений — тогда вызывающий код (fitArcLabel) переходит на внешнюю дугу.
 */
function fitInnerArcLabel(name: string, pinRadius: number): { radius: number; fontSize: number } | null {
  const radius = pinRadius + ARC_BAND_INNER_INSET
  const bandAvailable = (pinRadius + HALO_GAP) - ARC_BAND_OUTER_MARGIN - radius
  const bandFontCap = Math.max(0, bandAvailable / BAND_ASCENT_RATIO)

  const budget = arcLength(radius) * ARC_FILL_RATIO
  const widthAtMax = measureTextWidth(name, '600', ARC_FONT_MAX)
  const lengthFontCap = widthAtMax > 0 ? ARC_FONT_MAX * (budget / widthAtMax) : ARC_FONT_MAX

  const fontSize = Math.min(ARC_FONT_MAX, bandFontCap, lengthFontCap)
  if (fontSize < ARC_FONT_MIN) return null
  return { radius, fontSize }
}

/**
 * Внешняя дуга (правило выбора радиуса, шаг 2-3 — см. комментарий модуля):
 * стартует сразу за внешним краем ореола (ARC_OUTER_INSET) и, если имя всё
 * равно не влезает по длине даже на ARC_FONT_MIN, радиус увеличивается
 * шагами ARC_RADIUS_STEP — окружность растёт линейно с радиусом, поэтому
 * решение находится за конечное (обычно 0-1) число шагов. Толщина кольца под
 * текст (ARC_OUTER_BAND_THICKNESS) щедрее внутренней — снаружи нет соседнего
 * кольца, которое можно случайно задеть по высоте, единственное реальное
 * ограничение здесь — длина дуги. Никогда не возвращает "не влезло" — при
 * исчерпании ARC_RADIUS_MAX_STEPS просто отдаёт лучший найденный вариант
 * (на реальных именах городов этот потолок не достигается, см. отчёт задачи).
 */
function fitOuterArcLabel(name: string, pinRadius: number): { radius: number; fontSize: number } {
  const bandFontCap = Math.max(ARC_FONT_MIN, ARC_OUTER_BAND_THICKNESS / BAND_ASCENT_RATIO)
  const widthAtMax = measureTextWidth(name, '600', ARC_FONT_MAX)
  let radius = pinRadius + HALO_GAP + ARC_OUTER_INSET

  for (let step = 0; step <= ARC_RADIUS_MAX_STEPS; step++) {
    const budget = arcLength(radius) * ARC_FILL_RATIO
    const lengthFontCap = widthAtMax > 0 ? ARC_FONT_MAX * (budget / widthAtMax) : ARC_FONT_MAX
    const fontSize = Math.min(ARC_FONT_MAX, bandFontCap, lengthFontCap)
    if (fontSize >= ARC_FONT_MIN || step === ARC_RADIUS_MAX_STEPS) {
      return { radius, fontSize: Math.max(fontSize, ARC_FONT_MIN) }
    }
    radius += ARC_RADIUS_STEP
  }
  return { radius, fontSize: ARC_FONT_MIN } // недостижимо (цикл всегда возвращает раньше), но успокаивает TS
}

// Порог "заметно лучше" при сравнении кеглей внутренней/внешней дуги (px) —
// защита от того, чтобы шум округления (11.0 против 10.96) не переключал
// короткие имена на внешнюю дугу без всякой пользы для читаемости.
const OUTER_FONT_ADVANTAGE_THRESHOLD = 0.4

/**
 * Правило выбора радиуса дуги для одного пина — см. подробное объяснение в
 * комментарии модуля выше ("Правка владельца №2"). Не "внутренняя, пока не
 * провалилась по нижнему пределу" (это позволяло бы именам вроде "Ростов-на-
 * Дону" оставаться на внутренней дуге с кеглем 6-7 — формально "не ниже
 * читаемого предела", но заметно мельче соседних 11px и хуже читается), а
 * ЧЕСТНОЕ сравнение обоих вариантов:
 *  - если имя не влезает во внутреннюю дугу вообще (даже на ARC_FONT_MIN) —
 *    внешняя, без вариантов;
 *  - иначе считаем ОБА кегля (внутренний и внешний при БАЗОВОМ внешнем
 *    радиусе, без эскалации) и берём тот вариант, что дал БОЛЬШИЙ шрифт —
 *    внешняя дуга физически длиннее внутренней, поэтому для одного и того же
 *    имени почти всегда даёт кегль не меньше внутреннего; выигрывает она
 *    заметно (см. OUTER_FONT_ADVANTAGE_THRESHOLD) как раз на именах, которым
 *    внутренняя дуга тесна, но которые ещё формально "проходят" по нижнему
 *    пределу — то есть ровно на "больших названиях", а не только на
 *    экстремальных случаях;
 *  - короткие имена, которым внутренняя дуга и так даёт ARC_FONT_MAX
 *    (потолок кегля одинаков для обеих дуг — бо́льшая длина внешней дуги
 *    сверх потолка ничего не даёт), остаются на внутренней — ничьей владеет
 *    внутренняя, это и есть «короткие — как сейчас».
 * Итог соответствует правилу владельца буквально: короткие — внутри, длинные
 * — снаружи, граница между ними не догадка, а прямое сравнение кеглей.
 */
function fitArcLabel(name: string, pinRadius: number): { radius: number; fontSize: number; band: 'inner' | 'outer' } {
  const inner = fitInnerArcLabel(name, pinRadius)
  if (!inner) return { ...fitOuterArcLabel(name, pinRadius), band: 'outer' }

  const outerBase = fitOuterArcLabel(name, pinRadius)
  if (outerBase.fontSize > inner.fontSize + OUTER_FONT_ADVANTAGE_THRESHOLD) {
    return { ...outerBase, band: 'outer' }
  }
  return { ...inner, band: 'inner' }
}

// ── Раздвижка ВНЕШНИХ дуг по углу (см. комментарий модуля) ──────────────────

interface OuterArcLabel {
  id: string | number
  name: string
  cx: number
  cy: number
  radius: number
  fontSize: number
  halfAngleDeg: number
  centerAngleDeg: number
}

function angleToPoint(cx: number, cy: number, r: number, angleDeg: number): { x: number; y: number } {
  const rad = (angleDeg * Math.PI) / 180
  return { x: cx + r * Math.sin(rad), y: cy - r * Math.cos(rad) }
}

function halfAngleDegFor(width: number, radius: number): number {
  const angleRad = width / radius // длина дуги = radius * угол(рад)
  return Math.min(89, (angleRad * 180) / Math.PI / 2)
}

/** Приближённый прямоугольный бокс внешней подписи в АБСОЛЮТНЫХ координатах
 * карты (pin.x/pin.y — та же система, что использует declutterPins и
 * layoutPinLabels) — используется только для проверки пересечений, не для
 * рендера. x — по касательным в начале/конце занимаемой дуги (sin монотонен
 * на [-90,90]); y — по вершине (если 0° внутри диапазона) и по более
 * "боковой" из двух границ; с запасом по высоте символов на подъём/спуск
 * глифов. */
function outerLabelBox(l: OuterArcLabel): Box {
  const aStart = Math.max(-90, l.centerAngleDeg - l.halfAngleDeg)
  const aEnd = Math.min(90, l.centerAngleDeg + l.halfAngleDeg)
  const pStart = angleToPoint(l.cx, l.cy, l.radius, aStart)
  const pEnd = angleToPoint(l.cx, l.cy, l.radius, aEnd)
  const ys = [pStart.y, pEnd.y]
  if (aStart <= 0 && aEnd >= 0) ys.push(l.cy - l.radius)
  const xMin = Math.min(pStart.x, pEnd.x)
  const xMax = Math.max(pStart.x, pEnd.x)
  const yTopRaw = Math.min(...ys)
  const yBottomRaw = Math.max(...ys)
  const pad = l.fontSize * 0.75
  return { x: xMin - pad * 0.3, y: yTopRaw - pad, w: xMax - xMin + pad * 0.6, h: yBottomRaw - yTopRaw + pad * 1.3 }
}

/** Находит id внешних подписей, которые ПОСЛЕ раздвижки по углу всё ещё
 * пересекаются (друг с другом или с чужим ореолом) — эскалация радиуса в
 * layoutArcPinLabels применяется только к ним. */
function findOuterConflicts(labels: OuterArcLabel[], markers: { id: string | number; box: Box }[]): Set<string | number> {
  const conflicted = new Set<string | number>()
  for (const l of labels) {
    const lb = outerLabelBox(l)
    for (const m of markers) {
      if (m.id !== l.id && boxesOverlap(lb, m.box)) conflicted.add(l.id)
    }
  }
  for (let i = 0; i < labels.length; i++) {
    for (let j = i + 1; j < labels.length; j++) {
      if (boxesOverlap(outerLabelBox(labels[i]), outerLabelBox(labels[j]))) {
        conflicted.add(labels[i].id)
        conflicted.add(labels[j].id)
      }
    }
  }
  return conflicted
}

/** Раздвигает внешние подписи ПО УГЛУ начала текста вдоль их собственной
 * дуги (владелец: «разводи их по углу начала текста, а не прячь и не
 * уменьшай») — мутирует l.centerAngleDeg на месте. Аналог Y-раздвижки в
 * layoutPinLabels, но ось движения другая: изменение угла у вершины дуги
 * даёт почти горизонтальное смещение бокса (по касательной), поэтому величина
 * толчка в пикселях переводится в градусы через радиус конкретной подписи
 * (Δpx / radius, в радианах). Каждая подпись зажата в [-90+half, 90-half] —
 * не может уйти за 9 или 3 часа (иначе текст перевернётся, см. комментарий
 * модуля про верхнюю половину окружности). */
function resolveOuterArcAngles(labels: OuterArcLabel[], markers: { id: string | number; box: Box }[]) {
  const clampAngle = (l: OuterArcLabel, v: number) => Math.max(-90 + l.halfAngleDeg, Math.min(90 - l.halfAngleDeg, v))

  for (let pass = 0; pass < MAX_OUTER_PASSES; pass++) {
    let moved = false

    // 1) внешняя подпись vs ЧУЖОЙ ореол (не своего пина).
    for (const l of labels) {
      const lb = outerLabelBox(l)
      for (const m of markers) {
        if (m.id === l.id || !boxesOverlap(lb, m.box)) continue
        const markerCx = m.box.x + m.box.w / 2
        const dir = l.cx <= markerCx ? -1 : 1
        const pushPx = Math.min(lb.x + lb.w, m.box.x + m.box.w) - Math.max(lb.x, m.box.x) + OUTER_LABEL_GAP_PX
        const pushDeg = (pushPx / l.radius) * (180 / Math.PI)
        const next = clampAngle(l, l.centerAngleDeg + dir * pushDeg)
        if (Math.abs(next - l.centerAngleDeg) > 0.05) { l.centerAngleDeg = next; moved = true }
      }
    }

    // 2) внешняя подпись vs внешняя подпись другого пина.
    for (let i = 0; i < labels.length; i++) {
      for (let j = i + 1; j < labels.length; j++) {
        const a = labels[i]
        const b = labels[j]
        const ab = outerLabelBox(a)
        const bb = outerLabelBox(b)
        if (!boxesOverlap(ab, bb)) continue
        const overlapX = Math.min(ab.x + ab.w, bb.x + bb.w) - Math.max(ab.x, bb.x)
        const pushPx = overlapX / 2 + OUTER_LABEL_GAP_PX
        const aCx = ab.x + ab.w / 2
        const bCx = bb.x + bb.w / 2
        const dir = aCx <= bCx ? -1 : 1
        const aNext = clampAngle(a, a.centerAngleDeg + dir * (pushPx / a.radius) * (180 / Math.PI))
        const bNext = clampAngle(b, b.centerAngleDeg - dir * (pushPx / b.radius) * (180 / Math.PI))
        if (Math.abs(aNext - a.centerAngleDeg) > 0.05 || Math.abs(bNext - b.centerAngleDeg) > 0.05) {
          a.centerAngleDeg = aNext
          b.centerAngleDeg = bNext
          moved = true
        }
      }
    }

    if (!moved) break
  }
}

/**
 * Считает геометрию дуговых подписей: радиус дуги (внутренней — по бледной
 * части ореола, или внешней — за его краем для длинных имён, см. комментарий
 * модуля про правило выбора радиуса), подобранный кегль, "band" и
 * startOffsetPercent (позиция вдоль дуги — для внешних подписей могла быть
 * сдвинута раздвижкой resolveOuterArcAngles).
 *
 * Внутренние подписи в раздвижке не участвуют — их ореолы гарантированно не
 * пересекаются (см. declutterPins в FleetRegionsView.vue, HALO_GAP). Внешние
 * могут пересечься с соседями (сами ореолы близко — реальные кластеры Москва/
 * Подольск/Курск, Донецк/Курск/Ростов-на-Дону) — для них выполняется несколько
 * "раундов": раздвижка по углу (resolveOuterArcAngles), и если её не хватило
 * (оба конца дуги уже упёрлись в границы верхней половины) — увеличение
 * радиуса ТОЛЬКО у всё ещё конфликтующих пинов (findOuterConflicts) и повтор.
 * Ничего не прячется и не обрезается ни на одном из раундов.
 *
 * zoom не влияет на сам подбор кегля/раздвижку — обе величины (pin.radius,
 * pin.x/y) уже в "локальных"/абсолютных zoom-независимых координатах карты
 * (см. ArcLabelResult.radius, тот же принцип, что и в declutterPins/
 * layoutPinLabels) — параметр оставлен для единообразия сигнатуры.
 */
export function layoutArcPinLabels(pins: MapPin[], _zoom: number = 1): Map<string | number, ArcLabelResult> {
  const result = new Map<string | number, ArcLabelResult>()

  const markers = pins.map(p => ({
    id: p.id,
    box: { x: p.x - (p.radius + HALO_GAP), y: p.y - (p.radius + HALO_GAP), w: 2 * (p.radius + HALO_GAP), h: 2 * (p.radius + HALO_GAP) } as Box,
  }))

  const outerLabels: OuterArcLabel[] = []

  for (const p of pins) {
    if (!p.name) {
      result.set(p.id, { radius: p.radius + ARC_BAND_INNER_INSET, fontSize: ARC_FONT_MAX, band: 'inner', startOffsetPercent: 50 })
      continue
    }
    const fit = fitArcLabel(p.name, p.radius)
    if (fit.band === 'inner') {
      result.set(p.id, { radius: fit.radius, fontSize: fit.fontSize, band: 'inner', startOffsetPercent: 50 })
      continue
    }
    const textWidth = measureTextWidth(p.name, '600', fit.fontSize) * 1.04 // небольшой запас на антиалиасинг/кернинг
    outerLabels.push({
      id: p.id, name: p.name, cx: p.x, cy: p.y,
      radius: fit.radius, fontSize: fit.fontSize,
      halfAngleDeg: halfAngleDegFor(textWidth, fit.radius),
      centerAngleDeg: 0,
    })
  }

  // Раздвижка по углу + эскалация радиуса конфликтующих пинов (см. комментарий выше).
  for (let round = 0; round <= ARC_RADIUS_MAX_STEPS; round++) {
    resolveOuterArcAngles(outerLabels, markers)
    const conflicted = findOuterConflicts(outerLabels, markers)
    if (conflicted.size === 0 || round === ARC_RADIUS_MAX_STEPS) break
    for (const l of outerLabels) {
      if (!conflicted.has(l.id)) continue
      l.radius += ARC_RADIUS_STEP
      const textWidth = measureTextWidth(l.name, '600', l.fontSize) * 1.04
      l.halfAngleDeg = halfAngleDegFor(textWidth, l.radius)
      l.centerAngleDeg = 0 // на новом, более просторном радиусе начинаем раздвижку заново
    }
  }

  for (const l of outerLabels) {
    const startOffsetPercent = ((l.centerAngleDeg + 90) / 180) * 100
    result.set(l.id, { radius: l.radius, fontSize: l.fontSize, band: 'outer', startOffsetPercent })
  }

  return result
}
