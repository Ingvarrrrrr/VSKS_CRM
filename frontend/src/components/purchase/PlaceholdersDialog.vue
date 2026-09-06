<template>
  <!-- Phase 23: диалог «Доступные переменные шаблонов» -->
  <v-dialog v-model="open" max-width="960" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4 d-flex align-center">
        <v-icon icon="mdi-code-braces" class="mr-2" />Доступные переменные шаблонов
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="open = false" />
      </v-card-title>
      <v-divider />
      <v-card-text style="max-height:70vh">
        <div v-for="grp in placeholderGroups" :key="grp.title" class="mb-5">
          <div class="text-subtitle-2 font-weight-bold mb-2" style="color:#6200ea">{{ grp.title }}</div>
          <v-table density="compact">
            <thead>
              <tr>
                <th style="width:260px">Переменная</th>
                <th>Описание</th>
                <th style="width:200px">Пример</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in grp.items" :key="item.var">
                <td><code style="font-size:11px">{{ formatPlaceholder(item.var) }}</code></td>
                <td class="text-body-2">{{ item.desc }}</td>
                <td class="text-caption text-medium-emphasis">{{ item.ex }}</td>
              </tr>
            </tbody>
          </v-table>
        </div>
        <v-alert type="info" variant="tonal" density="compact" class="mt-3">
          Полный справочник с примерами и условными блоками: <code>backend/templates/PLACEHOLDERS.md</code>
        </v-alert>
      </v-card-text>
      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn @click="open = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'

const open = defineModel<boolean>({ default: false })
const { mobile } = useDisplay()

// Vue parser ломается на inline-выражении { '{{' + x + '}}' } (видит '}}' как конец интерполяции),
// поэтому формирование плейсхолдер-строки вынесено в функцию.
function formatPlaceholder(name: string): string {
  return '{' + '{' + name + '}' + '}'
}

const placeholderGroups = [
  {
    title: '🎯 Универсальный договор (auto-switch)',
    items: [
      { var: 'subject_kind', desc: 'Тип договора: services (если все позиции услуги) | goods (если есть товары или нет позиций)', ex: 'goods' },
      { var: '{% if subject_kind == \'goods\' %}', desc: 'Условный блок для договора поставки (Покупатель/Поставщик, Спецификация)', ex: 'Покупатель/Поставщик/Спецификация' },
      { var: '{% else %}', desc: 'Альтернативная ветка — договор услуг (Заказчик/Исполнитель, ТЗ)', ex: 'Заказчик/Исполнитель/ТЗ' },
    ],
  },
  {
    title: '📑 Договор (общее)',
    items: [
      { var: 'contract_number', desc: 'Номер договора', ex: '2026/15' },
      { var: 'contract_date', desc: 'Дата договора', ex: '28.04.2026' },
      { var: 'contract_date_day', desc: 'День', ex: '28' },
      { var: 'contract_date_month', desc: 'Месяц прописью', ex: 'апреля' },
      { var: 'contract_date_year', desc: 'Год', ex: '2026' },
      { var: 'contract_city', desc: 'Город заключения', ex: 'Москва' },
      { var: 'contract_price_num', desc: 'Цена (без символа ₽)', ex: '130 000,00' },
      { var: 'contract_price_words', desc: 'Цена прописью', ex: 'сто тридцать тысяч рублей 00 копеек' },
    ],
  },
  {
    title: '🏛 Заказчик (customer_*) — Phase 23',
    items: [
      { var: 'customer_full_name', desc: 'Полное наименование организации', ex: 'АНО «ВСКС»' },
      { var: 'customer_short_name', desc: 'Краткое (из кавычек)', ex: 'ВСКС' },
      { var: 'customer_inn', desc: 'ИНН', ex: '7700000001' },
      { var: 'customer_kpp', desc: 'КПП', ex: '770001001' },
      { var: 'customer_ogrn', desc: 'ОГРН', ex: '1027700000001' },
      { var: 'customer_address', desc: 'Юридический адрес', ex: 'г. Москва, ул. Ленина, д. 1' },
      { var: 'customer_bank_name', desc: 'Банк', ex: 'ПАО Сбербанк' },
      { var: 'customer_bik', desc: 'БИК', ex: '044525225' },
      { var: 'customer_settlement_account', desc: 'Расчётный счёт', ex: '40701810...' },
      { var: 'customer_correspondent_account', desc: 'Корр. счёт', ex: '30101810...' },
      { var: 'customer_signatory_position', desc: 'Должность подписанта', ex: 'Президент' },
      { var: 'customer_signatory_name_genitive', desc: 'ФИО в родительном падеже', ex: 'Козеева Евгения Викторовича' },
      { var: 'customer_signatory_initials', desc: 'Фамилия + инициалы', ex: 'Козеев Е.В.' },
      { var: 'customer_signatory_basis', desc: 'Основание полномочий', ex: 'Устава' },
    ],
  },
  {
    title: '🏢 Исполнитель (contractor_*)',
    items: [
      { var: 'contractor_full_name', desc: 'Полное наименование', ex: 'ООО «Ромашка»' },
      { var: 'contractor_short_name', desc: 'Краткое', ex: 'Ромашка' },
      { var: 'contractor_org_type', desc: 'Тип организации', ex: 'Юр.лицо / ИП' },
      { var: 'contractor_inn', desc: 'ИНН', ex: '7700000002' },
      { var: 'contractor_ogrn', desc: 'ОГРН', ex: '1027700000002' },
      { var: 'contractor_ogrnip', desc: 'ОГРНИП (только для ИП)', ex: '304770000000001' },
      { var: 'contractor_address', desc: 'Адрес', ex: 'г. Москва, ул. Садовая, д. 5' },
      { var: 'contractor_signatory_position', desc: 'Должность', ex: 'Директор' },
      { var: 'contractor_signatory_name_genitive', desc: 'ФИО в родительном', ex: 'Сидорова Петра Павловича' },
      { var: 'contractor_signatory_initials', desc: 'Инициалы', ex: 'Сидоров П.П.' },
      { var: 'contractor_bank_name', desc: 'Банк', ex: 'ПАО Сбербанк' },
      { var: 'contractor_settlement_account', desc: 'р/с', ex: '40702810...' },
      { var: 'contractor_bik', desc: 'БИК', ex: '044525225' },
    ],
  },
  {
    title: '💰 Цена и НДС',
    items: [
      { var: 'vat_applicable', desc: 'НДС применяется?', ex: 'true / false' },
      { var: 'vat_rate', desc: 'Ставка НДС, %', ex: '20' },
      { var: 'vat_amount_num', desc: 'Сумма НДС цифрами', ex: '21 666,67' },
      { var: 'vat_amount_words', desc: 'Сумма НДС прописью', ex: 'двадцать одна тысяча...' },
      { var: 'vat_exemption_article', desc: 'Статья освобождения', ex: 'п.2 ст.346.11 НК РФ' },
      { var: 'vat_info_line', desc: 'Готовая строка НДС', ex: 'В том числе НДС 20%: ...' },
    ],
  },
  {
    title: '📅 Сроки',
    items: [
      { var: 'service_term', desc: 'Готовая строка срока', ex: 'с 01.05.2026 по 31.05.2026' },
      { var: 'service_term_mode', desc: 'Режим', ex: 'range / duration / deadline' },
      { var: 'service_start_date', desc: 'Начало', ex: '01.05.2026' },
      { var: 'service_end_date', desc: 'Окончание', ex: '31.05.2026' },
      { var: 'service_deadline_date', desc: 'Крайняя дата', ex: '30.06.2026' },
      { var: 'service_term_days', desc: 'Количество дней', ex: '30' },
      { var: 'submission_deadline_datetime', desc: 'Дата+время завершения приёма заявок', ex: '25.04.2026 18:00' },
      { var: 'delivery_location', desc: 'Место оказания услуг', ex: 'г. Москва, ул. Ленина, д. 1' },
    ],
  },
  {
    title: '✅ Условия',
    items: [
      { var: 'third_party_involved', desc: 'Привлечение третьих лиц', ex: 'true / false' },
      { var: 'subsidy_agreement_text', desc: 'Текст соглашения Минтруда', ex: 'Соглашения № 149-2023...' },
      { var: 'service_subject', desc: 'Предмет услуг (синоним subject)', ex: 'оказание полиграфических услуг' },
    ],
  },
  {
    title: '📦 Позиции (таблица)',
    items: [
      { var: 'item.num', desc: 'Номер строки', ex: '1' },
      { var: 'item.name', desc: 'Наименование', ex: 'Ежедневник А5' },
      { var: 'item.quantity', desc: 'Количество', ex: '50' },
      { var: 'item.unit', desc: 'Единица измерения', ex: 'шт.' },
      { var: 'item.unit_price', desc: 'Цена за единицу', ex: '500,00 ₽' },
      { var: 'item.total_price', desc: 'Сумма строки', ex: '25 000,00 ₽' },
      { var: 'items_count', desc: 'Общее количество позиций', ex: '3' },
    ],
  },
  {
    title: '⚙️ Технические',
    items: [
      { var: 'today', desc: 'Сегодняшняя дата', ex: '04.05.2026' },
      { var: 'today_iso', desc: 'ISO-дата', ex: '2026-05-04' },
      { var: 'purchase_number', desc: 'Номер закупки', ex: '42' },
      { var: 'registry_number', desc: 'Реестровый номер', ex: 'РЕЕ-2026-00042' },
      { var: 'subject', desc: 'Предмет закупки', ex: 'Поставка оборудования' },
      { var: 'subsidy_name', desc: 'Субсидия', ex: 'ФАДМ_2026' },
    ],
  },
]
</script>
