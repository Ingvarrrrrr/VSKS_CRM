// Каталог доступных значков для редактора сопоставления «Кузов → значок»
// (VehicleBodyIconsDialog.vue). Отдельный файл от bodyTypeIcon.ts по Правилу
// №5 (модульность) — тут данные ДЛЯ ВЫБОРА значка человеком (превью + подпись),
// а bodyTypeIcon.ts хранит саму таблицу сопоставления и логику резолва.
//
// PNG-силуэты — полный список файлов из /public/vehicle-icons/ (19 штук).
// MDI-иконки — курируемый список: все значки, которые реально используются в
// BODY_TYPE_ICON_MAP (bodyTypeIcon.ts) плюс несколько частых транспортных
// иконок про запас — чтобы человек выбирал глазами из осмысленного набора, а
// не листал все ~7000 иконок @mdi/font. Имена проверены по установленной
// версии пакета (frontend/node_modules/@mdi/font, 7.4.47).

export interface IconOption {
  kind: 'img' | 'mdi'
  value: string
  label: string
}

export const IMG_ICON_OPTIONS: IconOption[] = [
  { kind: 'img', value: 'sedan', label: 'Седан' },
  { kind: 'img', value: 'hatchback', label: 'Хэтчбек' },
  { kind: 'img', value: 'wagon', label: 'Универсал' },
  { kind: 'img', value: 'car_light', label: 'Легковая (общий силуэт)' },
  { kind: 'img', value: 'suv', label: 'Внедорожник' },
  { kind: 'img', value: 'pickup', label: 'Пикап' },
  { kind: 'img', value: 'minivan', label: 'Минивэн' },
  { kind: 'img', value: 'microbus', label: 'Микроавтобус' },
  { kind: 'img', value: 'truck_van', label: 'Фургон' },
  { kind: 'img', value: 'truck_tank', label: 'Автоцистерна' },
  { kind: 'img', value: 'truck_metal', label: 'Самосвал' },
  { kind: 'img', value: 'bus', label: 'Автобус' },
  { kind: 'img', value: 'trailer', label: 'Прицеп' },
  { kind: 'img', value: 'moped', label: 'Мопед' },
  { kind: 'img', value: 'quadbike', label: 'Квадроцикл' },
  { kind: 'img', value: 'snowmobile', label: 'Снегоход' },
  { kind: 'img', value: 'ambulance', label: 'Скорая помощь' },
  { kind: 'img', value: 'fire_truck', label: 'Пожарная машина' },
  { kind: 'img', value: 'other', label: 'Прочее (общий силуэт)' },
]

export const MDI_ICON_OPTIONS: IconOption[] = [
  { kind: 'mdi', value: 'mdi-car', label: 'Легковая машина' },
  { kind: 'mdi', value: 'mdi-car-sports', label: 'Спорткар / купе' },
  { kind: 'mdi', value: 'mdi-car-convertible', label: 'Кабриолет' },
  { kind: 'mdi', value: 'mdi-car-limousine', label: 'Лимузин' },
  { kind: 'mdi', value: 'mdi-taxi', label: 'Такси' },
  { kind: 'mdi', value: 'mdi-car-emergency', label: 'Экстренная машина (полиция и т.п.)' },
  { kind: 'mdi', value: 'mdi-car-multiple', label: 'Несколько машин (автовоз)' },
  { kind: 'mdi', value: 'mdi-van-utility', label: 'Служебный фургон' },
  { kind: 'mdi', value: 'mdi-van-passenger', label: 'Пассажирский фургон' },
  { kind: 'mdi', value: 'mdi-truck', label: 'Грузовик' },
  { kind: 'mdi', value: 'mdi-truck-flatbed', label: 'Грузовик с открытой платформой' },
  { kind: 'mdi', value: 'mdi-truck-trailer', label: 'Тягач с прицепом' },
  { kind: 'mdi', value: 'mdi-truck-cargo-container', label: 'Контейнеровоз' },
  { kind: 'mdi', value: 'mdi-truck-delivery', label: 'Грузовик доставки' },
  { kind: 'mdi', value: 'mdi-truck-fast', label: 'Грузовик (скоростной)' },
  { kind: 'mdi', value: 'mdi-truck-off-road', label: 'Внедорожный грузовик' },
  { kind: 'mdi', value: 'mdi-dump-truck', label: 'Самосвал' },
  { kind: 'mdi', value: 'mdi-tanker-truck', label: 'Автоцистерна' },
  { kind: 'mdi', value: 'mdi-tow-truck', label: 'Эвакуатор' },
  { kind: 'mdi', value: 'mdi-crane', label: 'Автокран' },
  { kind: 'mdi', value: 'mdi-forklift', label: 'Погрузчик' },
  { kind: 'mdi', value: 'mdi-tractor', label: 'Трактор' },
  { kind: 'mdi', value: 'mdi-bus', label: 'Автобус' },
  { kind: 'mdi', value: 'mdi-bus-school', label: 'Школьный автобус' },
  { kind: 'mdi', value: 'mdi-bus-electric', label: 'Троллейбус / электробус' },
  { kind: 'mdi', value: 'mdi-tram', label: 'Трамвай' },
  { kind: 'mdi', value: 'mdi-motorbike', label: 'Мотоцикл' },
  { kind: 'mdi', value: 'mdi-moped', label: 'Мопед' },
  { kind: 'mdi', value: 'mdi-scooter', label: 'Скутер' },
  { kind: 'mdi', value: 'mdi-bike', label: 'Велосипед' },
  { kind: 'mdi', value: 'mdi-golf-cart', label: 'Багги / гольф-кар' },
  { kind: 'mdi', value: 'mdi-sail-boat', label: 'Плавсредство (лодка / гидроцикл)' },
  { kind: 'mdi', value: 'mdi-rowing', label: 'Гребная лодка' },
]
