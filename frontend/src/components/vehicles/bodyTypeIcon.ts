// Сопоставление «Кузов» (body_type) → силуэт для hero-плашки карточки ТС.
//
// Источник списка значений: backend/app/services/vehicle_sheet_dictionaries.py
// (BODY_TYPE_OPTIONS, 49 значений + NO_DATA_LABEL). Файл держим отдельно от
// VehicleDetailView.vue / VehicleTypeIcon.vue по Правилу №5 (модульность) —
// таблица сопоставления самостоятельна и её проще проверять/редактировать
// целиком, не листая огромный файл карточки.
//
// Кузов побеждает «Тип ТС» в приоритете hero-плашки (см. VehicleDetailView.vue),
// потому что описывает силуэт точнее (2026-09, запрос владельца).
//
// img.file  — PNG без расширения в /public/vehicle-icons/.
// mdi.icon  — имя иконки из @mdi/font (используется, когда точного силуэта
//             в ИИ-наборе нет — специально, а не молчаливый пропуск).

export const NO_DATA_LABEL = 'Нет данных'

export type BodyTypeIconResult =
  | { kind: 'img'; file: string }
  | { kind: 'mdi'; icon: string }

const IMG = (file: string): BodyTypeIconResult => ({ kind: 'img', file })
const MDI = (icon: string): BodyTypeIconResult => ({ kind: 'mdi', icon })

export const BODY_TYPE_ICON_MAP: Record<string, BodyTypeIconResult> = {
  // ── Легковые ──
  'Седан': IMG('sedan'),
  'Хэтчбек': IMG('hatchback'),
  'Универсал': IMG('wagon'),
  'Лифтбек': IMG('hatchback'),               // отдельного силуэта лифтбека в наборе нет — хэтчбек ближе всего
  'Купе': MDI('mdi-car-sports'),
  'Кабриолет': MDI('mdi-car-convertible'),
  'Родстер': MDI('mdi-car-convertible'),
  'Тарга': MDI('mdi-car-convertible'),
  'Лимузин': MDI('mdi-car-limousine'),

  // ── Фургоны и микроавтобусы ──
  'Минивэн': IMG('minivan'),
  'Микроавтобус': IMG('microbus'),
  'Фургон': IMG('truck_van'),
  'Тентованный': IMG('truck_van'),           // силуэт закрытого кузова — ближайшая замена тенту
  'Рефрижератор': IMG('truck_van'),
  'Изотермический': IMG('truck_van'),
  'Промтоварный': IMG('truck_van'),

  // ── Грузовые ──
  'Пикап': IMG('pickup'),
  'Бортовой': MDI('mdi-truck-flatbed'),
  // Автовоз (владелец, 2026-09): раньше был обозначен той же бортовой платформой,
  // что и «Бортовой» — визуально неотличимо, к тому же автовоз возит машины, а не
  // открытый груз. mdi-car-multiple («несколько машин») читается однозначно.
  'Автовоз': MDI('mdi-car-multiple'),
  'Эвакуатор': MDI('mdi-tow-truck'),
  'Цистерна': IMG('truck_tank'),
  'Самосвал': IMG('truck_metal'),
  'Бетономешалка': MDI('mdi-truck'),         // отдельной иконки бетономешалки в mdi нет
  // Мусоровоз (владелец, 2026-09): mdi-trash-can — пиктограмма ПОНЯТИЯ «мусор»,
  // а не машины. Заменено на обычный грузовик (машина, а не корзина).
  'Мусоровоз': MDI('mdi-truck'),
  'Седельный тягач': MDI('mdi-truck-trailer'),
  'Шасси': MDI('mdi-truck'),
  'Контейнеровоз': MDI('mdi-truck-cargo-container'),
  'Лесовоз': MDI('mdi-truck-flatbed'),
  // Трубовоз (найдено самостоятельно при ревизии, 2026-09): mdi-pipe — пиктограмма
  // самой трубы, а не машины. Заменено на грузовик-платформу (перевозит длинномер,
  // как и «Лесовоз» рядом).
  'Трубовоз': MDI('mdi-truck-flatbed'),
  'Тяжеловоз': MDI('mdi-truck-trailer'),

  // ── Спецтехника ──
  'Автокран': MDI('mdi-crane'),
  // Бурильная установка (найдено самостоятельно при ревизии, 2026-09): было
  // mdi-water-well — пиктограмма СООРУЖЕНИЯ (колодец/скважина), не машины;
  // точной иконки буровой установки в mdi нет — честнее показать просто грузовик
  // (это тоже техника на шасси), чем вводящий в заблуждение колодец.
  'Бурильная установка': MDI('mdi-truck'),
  'Погрузчик': MDI('mdi-forklift'),

  // ── Экстренные и служебные ──
  'Пожарный': IMG('fire_truck'),
  'Скорая помощь': IMG('ambulance'),
  'Полицейский': MDI('mdi-car-emergency'),
  // Инкассаторский (владелец, 2026-09): mdi-bank — пиктограмма ЗДАНИЯ банка, а не
  // машины. Заменено на служебный фургон (van-utility ближе всего к инкассаторской машине).
  'Инкассаторский': MDI('mdi-van-utility'),

  // ── Автобусы и электротранспорт ──
  'Городской автобус': IMG('bus'),
  'Междугородний автобус': IMG('bus'),
  'Школьный автобус': MDI('mdi-bus-school'),
  'Троллейбус': MDI('mdi-bus-electric'),
  'Трамвай': MDI('mdi-tram'),

  // ── Мото и внедорожная техника ──
  'Мотоцикл': MDI('mdi-motorbike'),          // силуэта классического мотоцикла в присланном наборе нет (файл motorcycle.png оказался с другим содержимым — см. отчёт)
  'Мопед': IMG('moped'),
  'Скутер': MDI('mdi-scooter'),
  'Квадроцикл': IMG('quadbike'),
  'Багги': MDI('mdi-golf-cart'),             // ближайший смысловой аналог лёгкого открытого багги
  'Снегоход': IMG('snowmobile'),
  // Гидроцикл (владелец, 2026-09): mdi-ski-water — лыжник за катером (человек,
  // а не транспорт). В установленной версии @mdi/font (7.4.47) нет mdi-jet-ski —
  // ближайшее плавсредство-пиктограмма транспорта — mdi-sail-boat.
  'Гидроцикл': MDI('mdi-sail-boat'),
}

/**
 * Группировка 49 значений «Кузов» по смыслу — для редактора значков
 * (VehicleBodyIconsDialog.vue) и любых будущих списков. Каждое значение
 * BODY_TYPE_OPTIONS (см. backend/app/services/vehicle_sheet_dictionaries.py)
 * встречается ровно в одной группе, включая NO_DATA_LABEL — владелец
 * (2026-09) явно попросил редактор на все 49 строк, не 48.
 */
export interface BodyTypeGroup {
  key: string
  title: string
  items: string[]
}

// Автоблок (2026-09): владелец попросил отсортировать «Кузов» по алфавиту.
// Группировка по смыслу (редактор значков, VehicleBodyIconsDialog.vue) — не
// трогается, сортировка — ТОЛЬКО внутри каждой группы (localeCompare('ru')
// корректно ставит «Ё» на словарное место, как и BODY_TYPE_OPTIONS на бэкенде).
const _BODY_TYPE_GROUPS_RAW: BodyTypeGroup[] = [
  {
    key: 'passenger', title: 'Легковые',
    items: ['Седан', 'Хэтчбек', 'Универсал', 'Лифтбек', 'Купе', 'Кабриолет', 'Родстер', 'Тарга', 'Лимузин'],
  },
  {
    key: 'vans', title: 'Фургоны и микроавтобусы',
    items: ['Минивэн', 'Микроавтобус', 'Фургон', 'Тентованный', 'Рефрижератор', 'Изотермический', 'Промтоварный'],
  },
  {
    key: 'trucks', title: 'Грузовые',
    items: [
      'Пикап', 'Бортовой', 'Автовоз', 'Эвакуатор', 'Цистерна', 'Самосвал',
      'Бетономешалка', 'Мусоровоз', 'Шасси', 'Контейнеровоз', 'Лесовоз', 'Трубовоз',
    ],
  },
  {
    key: 'special_emergency', title: 'Спецтехника и экстренные',
    items: [
      'Автокран', 'Бурильная установка', 'Погрузчик',
      'Пожарный', 'Скорая помощь', 'Полицейский', 'Инкассаторский',
    ],
  },
  {
    key: 'buses', title: 'Автобусы и электротранспорт',
    items: ['Городской автобус', 'Междугородний автобус', 'Школьный автобус', 'Троллейбус', 'Трамвай'],
  },
  {
    key: 'moto_offroad', title: 'Мото и внедорожная',
    items: ['Мотоцикл', 'Мопед', 'Скутер', 'Квадроцикл', 'Багги', 'Снегоход', 'Гидроцикл'],
  },
  {
    key: 'trailers', title: 'Прицепы и тягачи',
    items: ['Седельный тягач', 'Тяжеловоз'],
  },
  {
    key: 'other', title: 'Прочее',
    items: [NO_DATA_LABEL],
  },
]

export const BODY_TYPE_GROUPS: BodyTypeGroup[] = _BODY_TYPE_GROUPS_RAW.map(g => ({
  ...g,
  items: [...g.items].sort((a, b) => a.localeCompare(b, 'ru')),
}))

/**
 * Возвращает силуэт для значения поля «Кузов» либо null, если кузов не
 * заполнен / равен NO_DATA_LABEL / не найден в справочнике (тогда
 * VehicleTypeIcon должен откатиться на силуэт по «Типу ТС»).
 */
export function resolveBodyTypeIcon(bodyType?: string | null): BodyTypeIconResult | null {
  if (!bodyType) return null
  if (bodyType === NO_DATA_LABEL) return null
  return BODY_TYPE_ICON_MAP[bodyType] ?? null
}
