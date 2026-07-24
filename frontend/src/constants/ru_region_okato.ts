/**
 * Справочник субъектов РФ: код ОКАТО + федеральный округ.
 * Названия — РОВНО как в RUSSIAN_REGIONS (russian_regions.ts).
 * Зеркало backend/app/services/ru_regions.py (сверка — .tmp_test/check_regions_sync.py).
 * Коды ОКАТО — ОК 019-95; для АО полный префикс (НАО 11100, ХМАО 71100, ЯНАО 71140),
 * новые регионы: ДНР 21, Запорожская 23, ЛНР 43, Херсонская 74; Крым 35, Севастополь 67.
 */
export interface RegionOkatoInfo {
  /** Префикс ОКАТО субъекта (2 или 5 цифр; до 11 добивается нулями на backend) */
  okato: string
  /** Федеральный округ */
  district: string
}

const CFO = 'Центральный федеральный округ'
const SZFO = 'Северо-Западный федеральный округ'
const UFO = 'Южный федеральный округ'
const SKFO = 'Северо-Кавказский федеральный округ'
const PFO = 'Приволжский федеральный округ'
const URFO = 'Уральский федеральный округ'
const SFO = 'Сибирский федеральный округ'
const DFO = 'Дальневосточный федеральный округ'

export const RU_REGION_OKATO: Record<string, RegionOkatoInfo> = {
  'Алтайский край': { okato: '01', district: SFO },
  'Амурская область': { okato: '10', district: DFO },
  'Архангельская область': { okato: '11', district: SZFO },
  'Астраханская область': { okato: '12', district: UFO },
  'Белгородская область': { okato: '14', district: CFO },
  'Брянская область': { okato: '15', district: CFO },
  'Владимирская область': { okato: '17', district: CFO },
  'Волгоградская область': { okato: '18', district: UFO },
  'Вологодская область': { okato: '19', district: SZFO },
  'Воронежская область': { okato: '20', district: CFO },
  'Донецкая Народная Республика': { okato: '21', district: UFO },
  'Еврейская автономная область': { okato: '99', district: DFO },
  'Забайкальский край': { okato: '76', district: DFO },
  'Запорожская область': { okato: '23', district: UFO },
  'Ивановская область': { okato: '24', district: CFO },
  'Иркутская область': { okato: '25', district: SFO },
  'Кабардино-Балкарская Республика': { okato: '83', district: SKFO },
  'Калининградская область': { okato: '27', district: SZFO },
  'Калужская область': { okato: '29', district: CFO },
  'Камчатский край': { okato: '30', district: DFO },
  'Карачаево-Черкесская Республика': { okato: '91', district: SKFO },
  'Кемеровская область — Кузбасс': { okato: '32', district: SFO },
  'Кировская область': { okato: '33', district: PFO },
  'Костромская область': { okato: '34', district: CFO },
  'Краснодарский край': { okato: '03', district: UFO },
  'Красноярский край': { okato: '04', district: SFO },
  'Курганская область': { okato: '37', district: URFO },
  'Курская область': { okato: '38', district: CFO },
  'Ленинградская область': { okato: '41', district: SZFO },
  'Липецкая область': { okato: '42', district: CFO },
  'Луганская Народная Республика': { okato: '43', district: UFO },
  'Магаданская область': { okato: '44', district: DFO },
  'Москва': { okato: '45', district: CFO },
  'Московская область': { okato: '46', district: CFO },
  'Мурманская область': { okato: '47', district: SZFO },
  'Ненецкий автономный округ': { okato: '11100', district: SZFO },
  'Нижегородская область': { okato: '22', district: PFO },
  'Новгородская область': { okato: '49', district: SZFO },
  'Новосибирская область': { okato: '50', district: SFO },
  'Омская область': { okato: '52', district: SFO },
  'Оренбургская область': { okato: '53', district: PFO },
  'Орловская область': { okato: '54', district: CFO },
  'Пензенская область': { okato: '56', district: PFO },
  'Пермский край': { okato: '57', district: PFO },
  'Приморский край': { okato: '05', district: DFO },
  'Псковская область': { okato: '58', district: SZFO },
  'Республика Адыгея': { okato: '79', district: UFO },
  'Республика Алтай': { okato: '84', district: SFO },
  'Республика Башкортостан': { okato: '80', district: PFO },
  'Республика Бурятия': { okato: '81', district: DFO },
  'Республика Дагестан': { okato: '82', district: SKFO },
  'Республика Ингушетия': { okato: '26', district: SKFO },
  'Республика Калмыкия': { okato: '85', district: UFO },
  'Республика Карелия': { okato: '86', district: SZFO },
  'Республика Коми': { okato: '87', district: SZFO },
  'Республика Крым': { okato: '35', district: UFO },
  'Республика Марий Эл': { okato: '88', district: PFO },
  'Республика Мордовия': { okato: '89', district: PFO },
  'Республика Саха (Якутия)': { okato: '98', district: DFO },
  'Республика Северная Осетия — Алания': { okato: '90', district: SKFO },
  'Республика Татарстан': { okato: '92', district: PFO },
  'Республика Тыва': { okato: '93', district: SFO },
  'Республика Хакасия': { okato: '95', district: SFO },
  'Ростовская область': { okato: '60', district: UFO },
  'Рязанская область': { okato: '61', district: CFO },
  'Самарская область': { okato: '36', district: PFO },
  'Санкт-Петербург': { okato: '40', district: SZFO },
  'Саратовская область': { okato: '63', district: PFO },
  'Сахалинская область': { okato: '64', district: DFO },
  'Свердловская область': { okato: '65', district: URFO },
  'Севастополь': { okato: '67', district: UFO },
  'Смоленская область': { okato: '66', district: CFO },
  'Ставропольский край': { okato: '07', district: SKFO },
  'Тамбовская область': { okato: '68', district: CFO },
  'Тверская область': { okato: '28', district: CFO },
  'Томская область': { okato: '69', district: SFO },
  'Тульская область': { okato: '70', district: CFO },
  'Тюменская область': { okato: '71', district: URFO },
  'Удмуртская Республика': { okato: '94', district: PFO },
  'Ульяновская область': { okato: '73', district: PFO },
  'Хабаровский край': { okato: '08', district: DFO },
  'Ханты-Мансийский автономный округ — Югра': { okato: '71100', district: URFO },
  'Херсонская область': { okato: '74', district: UFO },
  'Челябинская область': { okato: '75', district: URFO },
  'Чеченская Республика': { okato: '96', district: SKFO },
  'Чувашская Республика': { okato: '97', district: PFO },
  'Чукотский автономный округ': { okato: '77', district: DFO },
  'Ямало-Ненецкий автономный округ': { okato: '71140', district: URFO },
  'Ярославская область': { okato: '78', district: CFO },
}
