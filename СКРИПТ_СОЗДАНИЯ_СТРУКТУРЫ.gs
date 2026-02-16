/**
 * Скрипт для создания структуры базы данных в Google Sheets
 * Запускать один раз для инициализации структуры
 */

function createDatabaseStructure() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  
  // Удаляем существующие листы (если нужно пересоздать)
  // var sheets = ss.getSheets();
  // sheets.forEach(function(sheet) {
  //   if (sheet.getName() !== 'Структура') {
  //     ss.deleteSheet(sheet);
  //   }
  // });
  
  // Создаем листы
  createGoodsServiceSheet(ss);
  createContractItemsSheet(ss);
  createContractorsSheet(ss);
  createSubsidiesSheet(ss);
  createCategoriesFEOSheet(ss);
  createCategoriesAppSheet(ss);
  createPaymentsSheet(ss);
  createDocumentsSheet(ss);
  createDashboardSheet(ss);
  createRegistrySheet(ss);
  
  // Настраиваем зависимости
  setupDependencies(ss);
  
  // Настраиваем форматирование
  setupFormatting(ss);
  
  Logger.log('Структура базы данных создана успешно!');
}

/**
 * Создание листа GoodsService (основная таблица)
 */
function createGoodsServiceSheet(ss) {
  var sheet = getOrCreateSheet(ss, 'GoodsService');
  
  // Заголовки
  var headers = [
    'ID',
    'Номер договора',
    'Дата договора',
    'Тип договора',
    'Вид договора',
    'Субсидия_ID',
    'Номер закупки',
    'Номер заказа',
    'Предмет договора',
    'Детальное описание',
    'Контрагент_ID',
    'Статус договора',
    'Статус закупки',
    'Стадия исполнения',
    'Дата начала',
    'Дата окончания',
    'Срок исполнения',
    'НМЦК',
    'Цена без НДС',
    'Сумма НДС',
    'Цена с НДС',
    'Экономия',
    'Процент экономии',
    'Законтрактовано',
    'Поставлено',
    'Оплачено',
    'Остаток к оплате',
    'Остаток к поставке',
    'Применение НДС',
    'Ставка НДС',
    'Способ оплаты',
    'Форма оплаты',
    'Размер аванса',
    'Срок оплаты',
    'Направление расходов ФЭО',
    'Тип расходов ФЭО',
    'Направление из приложения',
    'Тип конкретизированный',
    'Ответственный',
    'Город',
    'Комментарии',
    'Дата создания',
    'Дата изменения',
    'Автор',
    'Редактор'
  ];
  
  // Устанавливаем заголовки
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  
  // Настраиваем ширину столбцов
  var columnWidths = [50, 120, 100, 120, 100, 80, 120, 120, 200, 300, 80, 120, 120, 150, 100, 100, 80, 120, 120, 100, 120, 100, 100, 120, 120, 120, 120, 120, 100, 80, 120, 120, 100, 100, 200, 200, 200, 200, 150, 100, 300, 120, 120, 150, 150];
  for (var i = 0; i < columnWidths.length && i < headers.length; i++) {
    sheet.setColumnWidth(i + 1, columnWidths[i]);
  }
  
  // Настраиваем выпадающие списки
  setupDataValidation(sheet, 4, ['Поставка', 'Услуги', 'ГПХ', 'Ремонт ТС']); // Тип договора
  setupDataValidation(sheet, 5, ['Разовый', 'Рамочный']); // Вид договора
  setupDataValidation(sheet, 12, ['Плановый', 'Подтвержденный', 'Ведутся работы', 'Исполнен', 'Расторгнут', 'Просрочен']); // Статус договора
  setupDataValidation(sheet, 13, ['Плановый', 'Подтвержденный', 'Ведутся работы']); // Статус закупки
  setupDataValidation(sheet, 29, ['Да', 'Нет']); // Применение НДС
  setupDataValidation(sheet, 31, ['Безналичный', 'Наличный']); // Способ оплаты
  setupDataValidation(sheet, 32, ['Предоплата', 'Постоплата', 'Поэтапная']); // Форма оплаты
  
  // Добавляем формулы
  addFormulasToGoodsService(sheet);
  
  Logger.log('Лист GoodsService создан');
}

/**
 * Создание листа Состав_договора
 */
function createContractItemsSheet(ss) {
  var sheet = getOrCreateSheet(ss, 'Состав_договора');
  
  var headers = [
    'ID',
    'Договор_ID',
    'Номер позиции',
    'Наименование',
    'Артикул',
    'Количество',
    'Ед. изм.',
    'Код ОКЕИ',
    'Цена за единицу',
    'Итоговая цена за единицу',
    'НДС %',
    'Сумма НДС',
    'Стоимость позиции',
    'Поставлено количество',
    'Оплачено',
    'Страна происхождения',
    'Производитель',
    'Гарантийный срок',
    'Технические характеристики',
    'Описание услуги',
    'Направление расходов ФЭО',
    'Тип расходов ФЭО',
    'Направление из приложения',
    'Тип конкретизированный',
    'Комментарии'
  ];
  
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  
  Logger.log('Лист Состав_договора создан');
}

/**
 * Создание листа Контрагенты
 */
function createContractorsSheet(ss) {
  var sheet = getOrCreateSheet(ss, 'Контрагенты');
  
  var headers = [
    'ID',
    'Контрагент',
    'Полное наименование',
    'ИНН',
    'КПП',
    'ОГРН',
    'ОКПО',
    'ОКТМО',
    'ФИО руководителя',
    'Должность руководителя',
    'Основание действия',
    'Номер доверенности',
    'Дата доверенности',
    'Кем выдана доверенность',
    'Расчётный счёт',
    'Кореспондентский счёт',
    'БИК банка',
    'Наименование банка',
    'Юридический адрес',
    'Почтовый адрес',
    'Фактический адрес',
    'Телефон организации',
    'Факс',
    'E-mail организации',
    'Веб-сайт',
    'Контактное лицо',
    'Должность контактного лица',
    'Телефон контактного лица',
    'E-mail контактного лица',
    'Дополнительные контакты',
    'Дата создания',
    'Дата изменения',
    'Активен'
  ];
  
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  
  setupDataValidation(sheet, 33, ['Да', 'Нет']); // Активен
  
  Logger.log('Лист Контрагенты создан');
}

/**
 * Создание листа Субсидии
 */
function createSubsidiesSheet(ss) {
  var sheet = getOrCreateSheet(ss, 'Субсидии');
  
  var headers = [
    'ID',
    'Наименование',
    'Краткое наименование',
    'Ведомство',
    'Год',
    'Общий объём',
    'Законтрактовано',
    'Планируется',
    'Поставлено',
    'Оплачено',
    'Остаток',
    'Активна'
  ];
  
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  
  setupDataValidation(sheet, 4, ['Минпрос', 'Минтруд', 'ФАДМ', 'Регионы']); // Ведомство
  setupDataValidation(sheet, 12, ['Да', 'Нет']); // Активна
  
  Logger.log('Лист Субсидии создан');
}

/**
 * Создание листа Категории_из_ФЭО
 */
function createCategoriesFEOSheet(ss) {
  var sheet = getOrCreateSheet(ss, 'Категории_из_ФЭО');
  
  // Структура будет заполняться вручную или через импорт
  var headers = ['Категория'];
  for (var i = 1; i <= 10; i++) {
    headers.push('Подкатегория_' + i);
  }
  
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  
  Logger.log('Лист Категории_из_ФЭО создан');
}

/**
 * Создание листа Категории_из_приложения
 */
function createCategoriesAppSheet(ss) {
  var sheet = getOrCreateSheet(ss, 'Категории_из_приложения');
  
  var headers = ['Категория'];
  for (var i = 1; i <= 10; i++) {
    headers.push('Подкатегория_' + i);
  }
  
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  
  Logger.log('Лист Категории_из_приложения создан');
}

/**
 * Создание листа Платежи
 */
function createPaymentsSheet(ss) {
  var sheet = getOrCreateSheet(ss, 'Платежи');
  
  var headers = [
    'ID',
    'Договор_ID',
    'Дата платежа',
    'Номер платежа',
    'Сумма',
    'Назначение',
    'Статус сверки',
    'Источник файла',
    'Дата загрузки',
    'Комментарии'
  ];
  
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  
  setupDataValidation(sheet, 7, ['Не сверен', 'Сверен', 'Ошибка']); // Статус сверки
  
  Logger.log('Лист Платежи создан');
}

/**
 * Создание листа Документы
 */
function createDocumentsSheet(ss) {
  var sheet = getOrCreateSheet(ss, 'Документы');
  
  var headers = [
    'ID',
    'Договор_ID',
    'Тип документа',
    'Название',
    'Номер',
    'Дата',
    'Ссылка на файл',
    'ID файла',
    'Комментарии'
  ];
  
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  
  var docTypes = ['Протокол', 'ТЗ', 'Спецификация', 'Акт', 'Счет', 'Счет-фактура', 'УПД', 'Накладная', 'Платежное поручение', 'Выписка'];
  setupDataValidation(sheet, 3, docTypes); // Тип документа
  
  Logger.log('Лист Документы создан');
}

/**
 * Создание листа Дашборд
 */
function createDashboardSheet(ss) {
  var sheet = getOrCreateSheet(ss, 'Дашборд');
  
  // Будет заполняться формулами и графиками
  sheet.getRange(1, 1).setValue('Дашборд');
  sheet.getRange(1, 1).setFontWeight('bold').setFontSize(16);
  
  Logger.log('Лист Дашборд создан');
}

/**
 * Создание листа Реестр_договоров
 */
function createRegistrySheet(ss) {
  var sheet = getOrCreateSheet(ss, 'Реестр_договоров');
  
  var headers = [
    'Номер договора',
    'Контрагент',
    'Предмет договора',
    'Субсидия',
    'Сумма договора',
    'Законтрактовано',
    'Поставлено',
    'Оплачено',
    'Статус',
    'Стадия'
  ];
  
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  
  Logger.log('Лист Реестр_договоров создан');
}

/**
 * Получить или создать лист
 */
function getOrCreateSheet(ss, sheetName) {
  var sheet = ss.getSheetByName(sheetName);
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
  }
  return sheet;
}

/**
 * Настройка выпадающих списков
 */
function setupDataValidation(sheet, column, values) {
  var range = sheet.getRange(2, column, sheet.getMaxRows() - 1, 1);
  var rule = SpreadsheetApp.newDataValidation()
    .requireValueInList(values)
    .setAllowInvalid(false)
    .build();
  range.setDataValidation(rule);
}

/**
 * Добавление формул в GoodsService
 */
function addFormulasToGoodsService(sheet) {
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return;
  
  // Формулы для строки 2 (пример)
  var row = 2;
  
  // Сумма НДС (столбец T)
  sheet.getRange(row, 20).setFormula('=IF(AC' + row + '="Да"; S' + row + '*AD' + row + '/100; 0)');
  
  // Цена с НДС (столбец U)
  sheet.getRange(row, 21).setFormula('=S' + row + '+T' + row);
  
  // Экономия (столбец V)
  sheet.getRange(row, 22).setFormula('=R' + row + '-U' + row);
  
  // Процент экономии (столбец W)
  sheet.getRange(row, 23).setFormula('=IF(R' + row + '>0; V' + row + '/R' + row + '*100; 0)');
  
  // Остаток к оплате (столбец AA)
  sheet.getRange(row, 27).setFormula('=U' + row + '-Z' + row);
  
  // Дата создания (столбец AP) - будет через триггер
  // Дата изменения (столбец AQ) - будет через триггер
}

/**
 * Настройка зависимостей категорий ФЭО
 */
function setupDependencies(ss) {
  // Зависимости будут настроены через функцию onEdit
  Logger.log('Зависимости будут настроены через onEdit');
}

/**
 * Настройка условного форматирования
 */
function setupFormatting(ss) {
  var sheet = ss.getSheetByName('GoodsService');
  if (!sheet) return;
  
  var statusColumn = 12; // Столбец L (Статус договора)
  var range = sheet.getRange(2, statusColumn, sheet.getMaxRows() - 1, 1);
  
  // Правила форматирования
  var rules = [
    {status: 'Плановый', color: '#FFFF00'},
    {status: 'Подтвержденный', color: '#4A86E8'},
    {status: 'Ведутся работы', color: '#6AA84F'},
    {status: 'Исполнен', color: '#CCCCCC'},
    {status: 'Расторгнут', color: '#FF0000'},
    {status: 'Просрочен', color: '#FF9900'}
  ];
  
  var conditionalFormatRules = [];
  
  rules.forEach(function(rule) {
    var conditionalFormatRule = SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo(rule.status)
      .setBackground(rule.color)
      .setRanges([range])
      .build();
    conditionalFormatRules.push(conditionalFormatRule);
  });
  
  sheet.setConditionalFormatRules(conditionalFormatRules);
  
  Logger.log('Условное форматирование настроено');
}



