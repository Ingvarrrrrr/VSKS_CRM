/** Default pins extracted from regions.html etalon — used as fallback in RussiaMapSvg. */

export interface MapPin {
  id: string | number
  name?: string
  sub?: string
  x: number
  y: number
  radius: number
  count: number
  color: string  // '#6aa6ff' (blue/филиал) | '#f6b34a' (warn/СТО) | '#22c997' (ok/регион) | '#8b5cf6' (purple/ФПГ)
  textColor?: string
}

export interface MapConnection {
  from: { x: number; y: number }
  to: { x: number; y: number }
}

export const DEFAULT_PINS: MapPin[] = [
  { id: 'msk',     name: 'ЦУ Москва',       sub: '9 ТС · филиал',  x: 180, y: 200, radius: 16, count: 9,  color: '#6aa6ff' },
  { id: 'rnd',     name: 'Ростов-на-Дону',  sub: '18 ТС · СТО',  x: 155, y: 250, radius: 22, count: 18, color: '#f6b34a' },
  { id: 'lnr',     name: 'Луганск (ЛНР)',   sub: '',              x: 190, y: 275, radius: 12, count: 6,  color: '#22c997' },
  { id: 'dnr',     name: 'Донецк (ДНР)',    sub: '',              x: 170, y: 290, radius: 11, count: 5,  color: '#22c997' },
  { id: 'zp',      name: 'Запорожье',       sub: '',              x: 140, y: 265, radius: 9,  count: 4,  color: '#8b5cf6' },
  { id: 'kursk',   name: 'Курск',           sub: '',              x: 160, y: 225, radius: 8,  count: 2,  color: '#5dd0ff' },
  { id: 'belg',    name: '',                sub: '',              x: 170, y: 235, radius: 6,  count: 1,  color: '#5dd0ff' },
  { id: 'irk',     name: 'Иркутск',         sub: '3 ТС · ФПГ',   x: 450, y: 200, radius: 9,  count: 3,  color: '#8b5cf6' },
  { id: 'tula',    name: '',                sub: '',              x: 195, y: 210, radius: 5,  count: 1,  color: '#5dd0ff' },
  { id: 'crimea',  name: 'Крым',            sub: '',              x: 115, y: 275, radius: 5,  count: 1,  color: '#5dd0ff' },
  { id: 'kherson', name: '',                sub: '',              x: 125, y: 290, radius: 5,  count: 1,  color: '#5dd0ff' },
]
