// contractorsTypes.ts — общие типы реестра контрагентов.
// Дословный перенос из ContractorsView.vue.

export interface ContractorWithStats {
  id: number
  name: string
  full_name?: string
  inn?: string
  kpp?: string
  address?: string
  contact_person?: string
  phone?: string
  org_phone?: string
  email?: string
  org_email?: string
  bank_details?: string
  signatory?: string
  signatory_basis?: string
  postal_address?: string
  ogrn?: string
  settlement_account?: string
  bank_name?: string
  bik?: string
  correspondent_account?: string
  product_categories: string[]
  manual_product_categories?: string[]
  org_type?: string
  passport_series?: string
  passport_number?: string
  passport_issuer?: string
  passport_issued_date?: string
  snils?: string
  registration_address?: string
  birth_date?: string
  website?: string
  registration_date?: string
  okpo?: string
  okved?: string
  treasury_account?: string
  single_treasury_account?: string
  signatory_position?: string
}

export interface ContractorTargetField {
  value: string
  title: string
  required: boolean
}

export const CONTRACTOR_TARGET_FIELDS: ContractorTargetField[] = [
  { value: 'name',                       title: 'Наименование',       required: true },
  { value: 'inn',                        title: 'ИНН',                required: false },
  { value: 'kpp',                        title: 'КПП',                required: false },
  { value: 'ogrn',                       title: 'ОГРН',               required: false },
  { value: 'org_type',                   title: 'Тип организации',    required: false },
  { value: 'address',                    title: 'Адрес',              required: false },
  { value: 'postal_address',             title: 'Почт. адрес',        required: false },
  { value: 'email',                      title: 'Email контакт. лица',    required: false },
  { value: 'phone',                      title: 'Телефон контакт. лица', required: false },
  { value: 'org_phone',                  title: 'Телефон организации',   required: false },
  { value: 'org_email',                  title: 'Email организации',     required: false },
  { value: 'contact_person',             title: 'Контактное лицо',       required: false },
  { value: 'signatory',                  title: 'Подписант',          required: false },
  { value: 'signatory_basis',            title: 'Основание',          required: false },
  { value: 'settlement_account',         title: 'Расч. счёт',         required: false },
  { value: 'bank_name',                  title: 'Банк',               required: false },
  { value: 'bik',                        title: 'БИК',                required: false },
  { value: 'correspondent_account',      title: 'Корр. счёт',         required: false },
  { value: 'manual_product_categories',  title: 'Категории товаров',  required: false },
  { value: 'website',                    title: 'Сайт организации',   required: false },
  { value: 'registration_date',          title: 'Дата регистрации',   required: false },
  { value: 'okpo',                       title: 'ОКПО',               required: false },
  { value: 'okved',                      title: 'ОКВЭД',              required: false },
  { value: 'treasury_account',           title: 'Казначейский счёт',  required: false },
  { value: 'single_treasury_account',    title: 'Единый казн. счёт',  required: false },
  { value: 'signatory_position',         title: 'Должность подписанта', required: false },
]
