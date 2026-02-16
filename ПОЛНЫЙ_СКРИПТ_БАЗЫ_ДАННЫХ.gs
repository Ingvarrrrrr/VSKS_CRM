/**
 * ПОЛНЫЙ СКРИПТ ДЛЯ БАЗЫ ДАННЫХ CRM СИСТЕМЫ
 * 
 * Этот файл содержит все необходимые функции:
 * - Создание структуры базы данных
 * - Настройка зависимостей категорий ФЭО
 * - Импорт данных из Google Sheets файла через GUI
 * 
 * ИНСТРУКЦИЯ:
 * 1. Скопируйте весь этот код в Apps Script
 * 2. Сохраните проект
 * 3. Запустите функцию createDatabaseStructure() для создания структуры
 * 4. Меню "Импорт данных" появится автоматически при открытии файла
 */

// ============================================================================
// СОЗДАНИЕ СТРУКТУРЫ БАЗЫ ДАННЫХ
// ============================================================================

/**
 * Основная функция создания структуры базы данных
 * Запускать один раз для инициализации структуры
 */
function createDatabaseStructure() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  
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
  
  // Создаем меню после создания структуры
  try {
    createMenu();
  } catch (error) {
    Logger.log('Ошибка при создании меню: ' + error.message);
  }
  
  var message = '✅ СТРУКТУРА БАЗЫ ДАННЫХ СОЗДАНА!\n\n';
  message += 'Создано листов: 10\n\n';
  message += '📋 СЛЕДУЮЩИЕ ШАГИ:\n\n';
  message += '1. Импортируйте данные:\n';
  message += '   - Используйте меню "📥 Импорт данных"\n';
  message += '   - Или запустите функцию quickImportFromCurrentFile()\n\n';
  message += '2. После импорта обновите выпадающие списки:\n';
  message += '   - Меню → "🔄 Обновить выпадающие списки ФЭО"\n';
  message += '   - Или запустите функцию updateFEODropdowns()\n\n';
  message += '3. Если меню не появилось:\n';
  message += '   - Обновите страницу (F5)\n';
  message += '   - Или запустите функцию createMenu() вручную';
  
  SpreadsheetApp.getUi().alert('Готово!', message, SpreadsheetApp.getUi().ButtonSet.OK);
}

/**
 * Создание листа GoodsService (основная таблица)
 */
function createGoodsServiceSheet(ss) {
  var sheet = getOrCreateSheet(ss, 'GoodsService');
  
  var headers = [
    'ID', 'Номер договора', 'Дата договора', 'Тип договора', 'Вид договора',
    'Субсидия_ID', 'Номер закупки', 'Номер заказа', 'Предмет договора', 'Детальное описание',
    'Контрагент_ID', 'Статус договора', 'Статус закупки', 'Стадия исполнения',
    'Дата начала', 'Дата окончания', 'Срок исполнения', 'НМЦК', 'Цена без НДС',
    'Сумма НДС', 'Цена с НДС', 'Экономия', 'Процент экономии', 'Законтрактовано',
    'Поставлено', 'Оплачено', 'Остаток к оплате', 'Остаток к поставке',
    'Применение НДС', 'Ставка НДС', 'Способ оплаты', 'Форма оплаты',
    'Размер аванса', 'Срок оплаты', 'Направление расходов ФЭО',
    'Тип расходов ФЭО', 'Направление из приложения', 'Тип конкретизированный',
    'Ответственный', 'Город', 'Комментарии', 'Дата создания',
    'Дата изменения', 'Автор', 'Редактор'
  ];
  
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  
  var columnWidths = [50, 120, 100, 120, 100, 80, 120, 120, 200, 300, 80, 120, 120, 150, 100, 100, 80, 120, 120, 100, 120, 100, 100, 120, 120, 120, 120, 120, 100, 80, 120, 120, 100, 100, 200, 200, 200, 200, 150, 100, 300, 120, 120, 150, 150];
  for (var i = 0; i < columnWidths.length && i < headers.length; i++) {
    sheet.setColumnWidth(i + 1, columnWidths[i]);
  }
  
  setupDataValidation(sheet, 4, ['Поставка', 'Услуги', 'ГПХ', 'Ремонт ТС']);
  setupDataValidation(sheet, 5, ['Разовый', 'Рамочный']);
  setupDataValidation(sheet, 12, ['Плановый', 'Подтвержденный', 'Ведутся работы', 'Исполнен', 'Расторгнут', 'Просрочен']);
  setupDataValidation(sheet, 13, ['Плановый', 'Подтвержденный', 'Ведутся работы']);
  setupDataValidation(sheet, 29, ['Да', 'Нет']);
  setupDataValidation(sheet, 31, ['Безналичный', 'Наличный']);
  setupDataValidation(sheet, 32, ['Предоплата', 'Постоплата', 'Поэтапная']);
  
  addFormulasToGoodsService(sheet);
  
  Logger.log('Лист GoodsService создан');
}

function createContractItemsSheet(ss) {
  var sheet = getOrCreateSheet(ss, 'Состав_договора');
  
  var headers = [
    'ID', 'Договор_ID', 'Номер позиции', 'Наименование', 'Артикул',
    'Количество', 'Ед. изм.', 'Код ОКЕИ', 'Цена за единицу',
    'Итоговая цена за единицу', 'НДС %', 'Сумма НДС', 'Стоимость позиции',
    'Поставлено количество', 'Оплачено', 'Страна происхождения',
    'Производитель', 'Гарантийный срок', 'Технические характеристики',
    'Описание услуги', 'Направление расходов ФЭО', 'Тип расходов ФЭО',
    'Направление из приложения', 'Тип конкретизированный', 'Комментарии'
  ];
  
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  
  Logger.log('Лист Состав_договора создан');
}

function createContractorsSheet(ss) {
  var sheet = getOrCreateSheet(ss, 'Контрагенты');
  
  var headers = [
    'ID', 'Контрагент', 'Полное наименование', 'ИНН', 'КПП', 'ОГРН',
    'ОКПО', 'ОКТМО', 'ФИО руководителя', 'Должность руководителя',
    'Основание действия', 'Номер доверенности', 'Дата доверенности',
    'Кем выдана доверенность', 'Расчётный счёт', 'Кореспондентский счёт',
    'БИК банка', 'Наименование банка', 'Юридический адрес',
    'Почтовый адрес', 'Фактический адрес', 'Телефон организации',
    'Факс', 'E-mail организации', 'Веб-сайт', 'Контактное лицо',
    'Должность контактного лица', 'Телефон контактного лица',
    'E-mail контактного лица', 'Дополнительные контакты',
    'Дата создания', 'Дата изменения', 'Активен'
  ];
  
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  
  setupDataValidation(sheet, 33, ['Да', 'Нет']);
  
  Logger.log('Лист Контрагенты создан');
}

function createSubsidiesSheet(ss) {
  var sheet = getOrCreateSheet(ss, 'Субсидии');
  
  var headers = [
    'ID', 'Наименование', 'Краткое наименование', 'Ведомство', 'Год',
    'Общий объём', 'Законтрактовано', 'Планируется', 'Поставлено',
    'Оплачено', 'Остаток', 'Активна'
  ];
  
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  
  setupDataValidation(sheet, 4, ['Минпрос', 'Минтруд', 'ФАДМ', 'Регионы']);
  setupDataValidation(sheet, 12, ['Да', 'Нет']);
  
  Logger.log('Лист Субсидии создан');
}

function createCategoriesFEOSheet(ss) {
  var sheet = getOrCreateSheet(ss, 'Категории_из_ФЭО');
  
  var headers = ['Категория'];
  for (var i = 1; i <= 10; i++) {
    headers.push('Подкатегория_' + i);
  }
  
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  
  Logger.log('Лист Категории_из_ФЭО создан');
}

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

function createPaymentsSheet(ss) {
  var sheet = getOrCreateSheet(ss, 'Платежи');
  
  var headers = [
    'ID', 'Договор_ID', 'Дата платежа', 'Номер платежа', 'Сумма',
    'Назначение', 'Статус сверки', 'Источник файла', 'Дата загрузки', 'Комментарии'
  ];
  
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  
  setupDataValidation(sheet, 7, ['Не сверен', 'Сверен', 'Ошибка']);
  
  Logger.log('Лист Платежи создан');
}

function createDocumentsSheet(ss) {
  var sheet = getOrCreateSheet(ss, 'Документы');
  
  var headers = [
    'ID', 'Договор_ID', 'Тип документа', 'Название', 'Номер',
    'Дата', 'Ссылка на файл', 'ID файла', 'Комментарии'
  ];
  
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  
  var docTypes = ['Протокол', 'ТЗ', 'Спецификация', 'Акт', 'Счет', 'Счет-фактура', 'УПД', 'Накладная', 'Платежное поручение', 'Выписка'];
  setupDataValidation(sheet, 3, docTypes);
  
  Logger.log('Лист Документы создан');
}

function createDashboardSheet(ss) {
  var sheet = getOrCreateSheet(ss, 'Дашборд');
  sheet.getRange(1, 1).setValue('Дашборд');
  sheet.getRange(1, 1).setFontWeight('bold').setFontSize(16);
  Logger.log('Лист Дашборд создан');
}

function createRegistrySheet(ss) {
  var sheet = getOrCreateSheet(ss, 'Реестр_договоров');
  
  var headers = [
    'Номер договора', 'Контрагент', 'Предмет договора', 'Субсидия',
    'Сумма договора', 'Законтрактовано', 'Поставлено', 'Оплачено', 'Статус', 'Стадия'
  ];
  
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  
  Logger.log('Лист Реестр_договоров создан');
}

function getOrCreateSheet(ss, sheetName) {
  var sheet = ss.getSheetByName(sheetName);
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
  }
  return sheet;
}

function setupDataValidation(sheet, column, values) {
  var range = sheet.getRange(2, column, sheet.getMaxRows() - 1, 1);
  var rule = SpreadsheetApp.newDataValidation()
    .requireValueInList(values)
    .setAllowInvalid(false)
    .build();
  range.setDataValidation(rule);
}

function addFormulasToGoodsService(sheet) {
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return;
  
  var row = 2;
  sheet.getRange(row, 20).setFormula('=IF(AC' + row + '="Да"; S' + row + '*AD' + row + '/100; 0)');
  sheet.getRange(row, 21).setFormula('=S' + row + '+T' + row);
  sheet.getRange(row, 22).setFormula('=R' + row + '-U' + row);
  sheet.getRange(row, 23).setFormula('=IF(R' + row + '>0; V' + row + '/R' + row + '*100; 0)');
  sheet.getRange(row, 27).setFormula('=U' + row + '-Z' + row);
}

function setupDependencies(ss) {
  // Настраиваем начальные выпадающие списки для категорий ФЭО
  setupInitialFEODropdowns(ss);
  Logger.log('Зависимости будут настроены через onEdit');
}

/**
 * Настройка начальных выпадающих списков для категорий ФЭО
 * Заполняет список категорий из справочника
 */
function setupInitialFEODropdowns(ss) {
  try {
    var goodsServiceSheet = ss.getSheetByName('GoodsService');
    if (!goodsServiceSheet) return;
    
    // Столбец AI (35) - Направление расходов ФЭО
    var categorySheet = ss.getSheetByName('Категории_из_ФЭО');
    if (categorySheet && categorySheet.getLastRow() > 1) {
      var categories = [];
      var categoryData = categorySheet.getDataRange().getValues();
      for (var i = 1; i < categoryData.length; i++) {
        if (categoryData[i][0] && categoryData[i][0].toString().trim() !== '') {
          categories.push(categoryData[i][0].toString().trim());
        }
      }
      
      if (categories.length > 0) {
        var range = goodsServiceSheet.getRange(2, 35, goodsServiceSheet.getMaxRows() - 1, 1);
        var rule = SpreadsheetApp.newDataValidation()
          .requireValueInList(categories)
          .setAllowInvalid(false)
          .build();
        range.setDataValidation(rule);
        Logger.log('Установлен список категорий ФЭО: ' + categories.length + ' элементов');
      }
    }
    
    // Столбец AK (37) - Направление из приложения
    var appCategorySheet = ss.getSheetByName('Категории_из_приложения');
    if (appCategorySheet && appCategorySheet.getLastRow() > 1) {
      var appCategories = [];
      var appCategoryData = appCategorySheet.getDataRange().getValues();
      for (var i = 1; i < appCategoryData.length; i++) {
        if (appCategoryData[i][0] && appCategoryData[i][0].toString().trim() !== '') {
          appCategories.push(appCategoryData[i][0].toString().trim());
        }
      }
      
      if (appCategories.length > 0) {
        var range = goodsServiceSheet.getRange(2, 37, goodsServiceSheet.getMaxRows() - 1, 1);
        var rule = SpreadsheetApp.newDataValidation()
          .requireValueInList(appCategories)
          .setAllowInvalid(false)
          .build();
        range.setDataValidation(rule);
        Logger.log('Установлен список категорий из приложения: ' + appCategories.length + ' элементов');
      }
    }
    
    // Аналогично для Состав_договора
    var contractItemsSheet = ss.getSheetByName('Состав_договора');
    if (contractItemsSheet) {
      if (categorySheet && categorySheet.getLastRow() > 1) {
        var categories = [];
        var categoryData = categorySheet.getDataRange().getValues();
        for (var i = 1; i < categoryData.length; i++) {
          if (categoryData[i][0] && categoryData[i][0].toString().trim() !== '') {
            categories.push(categoryData[i][0].toString().trim());
          }
        }
        
        if (categories.length > 0) {
          var range = contractItemsSheet.getRange(2, 21, contractItemsSheet.getMaxRows() - 1, 1);
          var rule = SpreadsheetApp.newDataValidation()
            .requireValueInList(categories)
            .setAllowInvalid(false)
            .build();
          range.setDataValidation(rule);
        }
      }
      
      if (appCategorySheet && appCategorySheet.getLastRow() > 1) {
        var appCategories = [];
        var appCategoryData = appCategorySheet.getDataRange().getValues();
        for (var i = 1; i < appCategoryData.length; i++) {
          if (appCategoryData[i][0] && appCategoryData[i][0].toString().trim() !== '') {
            appCategories.push(appCategoryData[i][0].toString().trim());
          }
        }
        
        if (appCategories.length > 0) {
          var range = contractItemsSheet.getRange(2, 23, contractItemsSheet.getMaxRows() - 1, 1);
          var rule = SpreadsheetApp.newDataValidation()
            .requireValueInList(appCategories)
            .setAllowInvalid(false)
            .build();
          range.setDataValidation(rule);
        }
      }
    }
    
  } catch (error) {
    Logger.log('Ошибка при настройке выпадающих списков ФЭО: ' + error.message);
  }
}

function setupFormatting(ss) {
  var sheet = ss.getSheetByName('GoodsService');
  if (!sheet) return;
  
  var statusColumn = 12;
  var range = sheet.getRange(2, statusColumn, sheet.getMaxRows() - 1, 1);
  
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

// ============================================================================
// ЗАВИСИМОСТИ КАТЕГОРИЙ ФЭО
// ============================================================================

/**
 * Обработчик события редактирования
 * Настраивает зависимости категорий ФЭО
 */
function onEdit(e) {
  if (!e) return;
  
  try {
    var sheet = e.source.getActiveSheet();
    var sheetName = sheet.getName();
    var editedColumn = e.range.getColumn();
    var editedRow = e.range.getRow();
    
    if (sheetName !== 'GoodsService' && sheetName !== 'Состав_договора') return;
    
    // GoodsService: столбцы AI(35), AJ(36), AK(37), AL(38)
    if (sheetName === 'GoodsService') {
      if (editedColumn === 35 && editedRow >= 2 && e.value) {
        updateFEOCategoryDependencies(sheet, editedRow, e.value, 'Категории_из_ФЭО', 36);
        clearDependentCells(sheet, editedRow, [36, 37, 38]);
      }
      if (editedColumn === 36 && editedRow >= 2 && e.value) {
        updateFEOCategoryDependencies(sheet, editedRow, e.value, 'Категории_из_ФЭО', 37);
        clearDependentCells(sheet, editedRow, [37, 38]);
      }
      if (editedColumn === 37 && editedRow >= 2 && e.value) {
        updateFEOCategoryDependencies(sheet, editedRow, e.value, 'Категории_из_приложения', 38);
        clearDependentCells(sheet, editedRow, [38]);
      }
    }
    
    // Состав_договора: столбцы U(21), V(22), W(23), X(24)
    if (sheetName === 'Состав_договора') {
      if (editedColumn === 21 && editedRow >= 2 && e.value) {
        updateFEOCategoryDependencies(sheet, editedRow, e.value, 'Категории_из_ФЭО', 22);
        clearDependentCells(sheet, editedRow, [22, 23, 24]);
      }
      if (editedColumn === 22 && editedRow >= 2 && e.value) {
        updateFEOCategoryDependencies(sheet, editedRow, e.value, 'Категории_из_ФЭО', 23);
        clearDependentCells(sheet, editedRow, [23, 24]);
      }
      if (editedColumn === 23 && editedRow >= 2 && e.value) {
        updateFEOCategoryDependencies(sheet, editedRow, e.value, 'Категории_из_приложения', 24);
        clearDependentCells(sheet, editedRow, [24]);
      }
    }
    
  } catch (error) {
    Logger.log('Ошибка в onEdit: ' + error.message);
  }
}

function updateFEOCategoryDependencies(sheet, row, selectedValue, categorySheetName, targetColumn) {
  try {
    var ss = sheet.getParent();
    var categorySheet = ss.getSheetByName(categorySheetName);
    
    if (!categorySheet) {
      Logger.log('Лист ' + categorySheetName + ' не найден');
      return;
    }
    
    var categoryData = categorySheet.getDataRange().getValues();
    if (categoryData.length < 2) {
      Logger.log('Нет данных в листе ' + categorySheetName);
      return;
    }
    
    var categoryIndex = -1;
    for (var i = 1; i < categoryData.length; i++) {
      if (categoryData[i][0] === selectedValue) {
        categoryIndex = i;
        break;
      }
    }
    
    if (categoryIndex === -1) {
      Logger.log('Категория "' + selectedValue + '" не найдена');
      return;
    }
    
    var subcategories = [];
    for (var col = 1; col < categoryData[0].length; col++) {
      var subcategory = categoryData[categoryIndex][col];
      if (subcategory && subcategory.toString().trim() !== '') {
        subcategories.push(subcategory.toString().trim());
      }
    }
    
    var targetRange = sheet.getRange(row, targetColumn);
    
    if (subcategories.length > 0) {
      var rule = SpreadsheetApp.newDataValidation()
        .requireValueInList(subcategories)
        .setAllowInvalid(false)
        .build();
      targetRange.setDataValidation(rule);
    } else {
      targetRange.removeDataValidation();
    }
    
  } catch (error) {
    Logger.log('Ошибка при обновлении зависимостей: ' + error.message);
  }
}

function clearDependentCells(sheet, row, columns) {
  columns.forEach(function(col) {
    sheet.getRange(row, col).clearContent();
    sheet.getRange(row, col).removeDataValidation();
  });
}

function initializeAllFEODependencies() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName('GoodsService');
  
  if (!sheet) return;
  
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return;
  
  for (var row = 2; row <= lastRow; row++) {
    var aiValue = sheet.getRange(row, 35).getValue();
    var ajValue = sheet.getRange(row, 36).getValue();
    var akValue = sheet.getRange(row, 37).getValue();
    
    if (aiValue) {
      updateFEOCategoryDependencies(sheet, row, aiValue.toString(), 'Категории_из_ФЭО', 36);
    }
    if (ajValue) {
      updateFEOCategoryDependencies(sheet, row, ajValue.toString(), 'Категории_из_ФЭО', 37);
    }
    if (akValue) {
      updateFEOCategoryDependencies(sheet, row, akValue.toString(), 'Категории_из_приложения', 38);
    }
  }
  
  Logger.log('Инициализация зависимостей завершена');
}

// ============================================================================
// ИМПОРТ ДАННЫХ С GUI
// ============================================================================

/**
 * Функция для создания меню при открытии таблицы
 * Вызывается автоматически при открытии файла
 */
function onOpen() {
  createMenu();
}

/**
 * Принудительное создание меню (можно вызвать вручную)
 */
function createMenu() {
  try {
    var ui = SpreadsheetApp.getUi();
    
    // Создаем меню
    var menu = ui.createMenu('📥 Импорт данных');
    menu.addItem('📂 Импорт из Google Sheets файла', 'showFileSelectionDialog');
    menu.addSeparator();
    menu.addItem('📄 Импорт из текущего файла', 'quickImportFromCurrentFile');
    menu.addSeparator();
    menu.addItem('🔄 Обновить выпадающие списки ФЭО', 'updateFEODropdowns');
    menu.addSeparator();
    menu.addItem('🔍 Диагностика системы', 'testAndFix');
    menu.addToUi();
    
    Logger.log('Меню создано успешно');
    
    // Показываем сообщение об успехе
    SpreadsheetApp.getUi().alert(
      'Меню создано',
      'Меню "📥 Импорт данных" успешно создано!\n\nИспользуйте его для импорта данных.',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    
  } catch (error) {
    Logger.log('Ошибка при создании меню: ' + error.message);
    var errorMsg = 'Не удалось создать меню: ' + error.message + '\n\nПопробуйте обновить страницу (F5)';
    SpreadsheetApp.getUi().alert('Ошибка', errorMsg, SpreadsheetApp.getUi().ButtonSet.OK);
  }
}

/**
 * Обновление выпадающих списков ФЭО после импорта данных
 */
function updateFEODropdowns() {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    setupInitialFEODropdowns(ss);
    
    SpreadsheetApp.getUi().alert(
      'Готово',
      'Выпадающие списки категорий ФЭО обновлены!\n\nТеперь в столбце "Направление расходов ФЭО" будут доступны категории из справочника.',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    
    Logger.log('Выпадающие списки ФЭО обновлены');
  } catch (error) {
    Logger.log('Ошибка при обновлении списков: ' + error.message);
    SpreadsheetApp.getUi().alert('Ошибка', 'Не удалось обновить списки: ' + error.message, SpreadsheetApp.getUi().ButtonSet.OK);
  }
}

/**
 * Показать диалог выбора файла
 */
function showFileSelectionDialog() {
  var html = HtmlService.createHtmlOutput(`
    <!DOCTYPE html>
    <html>
    <head>
      <base target="_top">
      <style>
        body { font-family: Arial, sans-serif; padding: 20px; background-color: #f5f5f5; }
        .container { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h2 { margin-top: 0; color: #1a73e8; }
        .search-box { width: 100%; padding: 10px; margin-bottom: 15px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
        .file-list { max-height: 300px; overflow-y: auto; border: 1px solid #ddd; border-radius: 4px; margin-bottom: 15px; }
        .file-item { padding: 10px; cursor: pointer; border-bottom: 1px solid #eee; transition: background-color 0.2s; }
        .file-item:hover { background-color: #f0f0f0; }
        .file-item.selected { background-color: #e3f2fd; border-left: 3px solid #1a73e8; }
        .file-name { font-weight: bold; color: #333; }
        .file-info { font-size: 12px; color: #666; margin-top: 5px; }
        .button-group { text-align: right; margin-top: 20px; }
        button { padding: 10px 20px; margin-left: 10px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
        .btn-primary { background-color: #1a73e8; color: white; }
        .btn-primary:hover { background-color: #1557b0; }
        .btn-secondary { background-color: #5f6368; color: white; }
        .btn-secondary:hover { background-color: #3c4043; }
        .loading { text-align: center; padding: 20px; color: #666; }
        .error { color: #d32f2f; padding: 10px; background-color: #ffebee; border-radius: 4px; margin-bottom: 15px; }
        .success { color: #388e3c; padding: 10px; background-color: #e8f5e9; border-radius: 4px; margin-bottom: 15px; }
      </style>
    </head>
    <body>
      <div class="container">
        <h2>Выбор файла для импорта</h2>
        <div id="errorMessage"></div>
        <div id="successMessage"></div>
        <input type="text" id="searchBox" class="search-box" placeholder="Поиск файлов по названию..." onkeyup="filterFiles()">
        <div class="file-list" id="fileList"><div class="loading">Загрузка файлов...</div></div>
        <div class="button-group">
          <button class="btn-secondary" onclick="google.script.host.close()">Отмена</button>
          <button class="btn-primary" onclick="importData()" id="importBtn" disabled>Импортировать</button>
        </div>
        <div id="result"></div>
      </div>
      <script>
        var selectedFileId = null;
        var files = [];
        window.onload = function() { loadFiles(); };
        function loadFiles() {
          google.script.run.withSuccessHandler(function(fileList) {
            files = fileList;
            displayFiles(fileList);
          }).withFailureHandler(function(error) {
            document.getElementById('fileList').innerHTML = '<div class="error">Ошибка загрузки файлов: ' + error.message + '</div>';
          }).getAvailableFiles();
        }
        function displayFiles(fileList) {
          var fileListDiv = document.getElementById('fileList');
          if (fileList.length === 0) {
            fileListDiv.innerHTML = '<div class="loading">Файлы не найдены</div>';
            return;
          }
          var html = '';
          fileList.forEach(function(file) {
            html += '<div class="file-item" onclick="selectFile(\'' + file.id + '\', this)" data-name="' + file.name.toLowerCase() + '">';
            html += '<div class="file-name">' + file.name + '</div>';
            html += '<div class="file-info">ID: ' + file.id + '</div></div>';
          });
          fileListDiv.innerHTML = html;
        }
        function selectFile(fileId, element) {
          var items = document.getElementsByClassName('file-item');
          for (var i = 0; i < items.length; i++) {
            items[i].classList.remove('selected');
          }
          element.classList.add('selected');
          selectedFileId = fileId;
          document.getElementById('importBtn').disabled = false;
        }
        function filterFiles() {
          var searchText = document.getElementById('searchBox').value.toLowerCase();
          var items = document.getElementsByClassName('file-item');
          for (var i = 0; i < items.length; i++) {
            var fileName = items[i].getAttribute('data-name');
            items[i].style.display = (fileName.indexOf(searchText) !== -1) ? '' : 'none';
          }
        }
        function importData() {
          if (!selectedFileId) {
            alert('Выберите файл для импорта!');
            return;
          }
          document.getElementById('importBtn').disabled = true;
          document.getElementById('importBtn').textContent = 'Импорт...';
          document.getElementById('result').innerHTML = '<div class="loading">Импорт данных...</div>';
          google.script.run.withSuccessHandler(function(result) {
            document.getElementById('importBtn').disabled = false;
            document.getElementById('importBtn').textContent = 'Импортировать';
            if (result.success) {
              var resultHtml = '<div class="success">Импорт завершен успешно!</div><div style="margin-top: 15px;"><p><strong>Результаты импорта:</strong></p><ul>';
              resultHtml += '<li>Субсидии: ' + result.results.subsidies + '</li>';
              resultHtml += '<li>Категории ФЭО: ' + result.results.categoriesFEO + '</li>';
              resultHtml += '<li>Категории из приложения: ' + result.results.categoriesApp + '</li>';
              resultHtml += '<li>Контрагенты: ' + result.results.contractors + '</li></ul></div>';
              document.getElementById('result').innerHTML = resultHtml;
              setTimeout(function() { google.script.host.close(); }, 3000);
            } else {
              document.getElementById('result').innerHTML = '<div class="error">Ошибка: ' + result.message + '</div>';
            }
          }).withFailureHandler(function(error) {
            document.getElementById('importBtn').disabled = false;
            document.getElementById('importBtn').textContent = 'Импортировать';
            document.getElementById('result').innerHTML = '<div class="error">Ошибка: ' + error.message + '</div>';
          }).importDataFromFile(selectedFileId);
        }
      </script>
    </body>
    </html>
  `).setWidth(600).setHeight(600).setTitle('Импорт данных из Google Sheets');
  
  SpreadsheetApp.getUi().showModalDialog(html, 'Выбор файла для импорта');
}

function getAvailableFiles() {
  try {
    var files = [];
    var searchTerms = ['Патриотика', 'патриотика', 'patriotika'];
    
    searchTerms.forEach(function(term) {
      var fileIterator = DriveApp.getFilesByName(term);
      while (fileIterator.hasNext()) {
        var file = fileIterator.next();
        if (file.getMimeType() === MimeType.GOOGLE_SHEETS) {
          var alreadyAdded = files.some(function(f) { return f.id === file.getId(); });
          if (!alreadyAdded) {
            files.push({ id: file.getId(), name: file.getName(), url: file.getUrl() });
          }
        }
      }
    });
    
    var allFiles = DriveApp.searchFiles('title contains "патриотика" and mimeType="application/vnd.google-apps.spreadsheet"');
    while (allFiles.hasNext()) {
      var file = allFiles.next();
      var alreadyAdded = files.some(function(f) { return f.id === file.getId(); });
      if (!alreadyAdded) {
        files.push({ id: file.getId(), name: file.getName(), url: file.getUrl() });
      }
    }
    
    if (files.length === 0) {
      var recentFiles = DriveApp.getFilesByType(MimeType.GOOGLE_SHEETS);
      var count = 0;
      while (recentFiles.hasNext() && count < 20) {
        var file = recentFiles.next();
        files.push({ id: file.getId(), name: file.getName(), url: file.getUrl() });
        count++;
      }
    }
    
    files.sort(function(a, b) { return a.name.localeCompare(b.name); });
    return files;
  } catch (error) {
    Logger.log('Ошибка при получении списка файлов: ' + error.message);
    return [];
  }
}

function importDataFromFile(fileId) {
  try {
    var file = DriveApp.getFileById(fileId);
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sourceSS = SpreadsheetApp.openById(fileId);
    
    var results = { subsidies: 0, categoriesFEO: 0, categoriesApp: 0, contractors: 0 };
    results.subsidies = importSubsidiesFromSource(sourceSS, ss);
    results.categoriesFEO = importCategoriesFEOFromSource(sourceSS, ss);
    results.categoriesApp = importCategoriesAppFromSource(sourceSS, ss);
    results.contractors = importContractorsFromSource(sourceSS, ss);
    
    return { success: true, message: 'Импорт завершен успешно', results: results };
  } catch (error) {
    Logger.log('Ошибка при импорте: ' + error.message);
    return { success: false, message: 'Ошибка: ' + error.message };
  }
}

function importFromCurrentFile() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var fileId = ss.getId();
  var result = importDataFromFile(fileId);
  
  if (result.success) {
    SpreadsheetApp.getUi().alert('Импорт завершен!', 'Импортировано:\nСубсидии: ' + result.results.subsidies + '\nКатегории ФЭО: ' + result.results.categoriesFEO + '\nКатегории из приложения: ' + result.results.categoriesApp + '\nКонтрагенты: ' + result.results.contractors, SpreadsheetApp.getUi().ButtonSet.OK);
  } else {
    SpreadsheetApp.getUi().alert('Ошибка', result.message, SpreadsheetApp.getUi().ButtonSet.OK);
  }
}

function importSubsidiesFromSource(sourceSS, targetSS) {
  try {
    var sourceSheet = sourceSS.getSheetByName('GoodsService');
    if (!sourceSheet) return 0;
    var targetSheet = targetSS.getSheetByName('Субсидии');
    if (!targetSheet) return 0;
    
    var dataRange = sourceSheet.getDataRange();
    var values = dataRange.getValues();
    if (values.length < 2) return 0;
    
    var headers = values[0];
    var subsidyColumnIndex = -1;
    var possibleNames = ['субсидия', 'subsidy', 'ведомство', 'department', 'направление', 'источник финансирования'];
    
    for (var i = 0; i < headers.length; i++) {
      var header = headers[i].toString().toLowerCase();
      for (var j = 0; j < possibleNames.length; j++) {
        if (header.indexOf(possibleNames[j]) !== -1) {
          subsidyColumnIndex = i;
          break;
        }
      }
      if (subsidyColumnIndex !== -1) break;
    }
    
    if (subsidyColumnIndex === -1) return 0;
    
    var subsidiesMap = {};
    for (var i = 1; i < values.length; i++) {
      var subsidyValue = values[i][subsidyColumnIndex];
      if (subsidyValue && subsidyValue.toString().trim() !== '') {
        var subsidyName = subsidyValue.toString().trim();
        if (!subsidiesMap[subsidyName]) {
          subsidiesMap[subsidyName] = {
            name: subsidyName,
            shortName: getShortName(subsidyName),
            department: determineDepartment(subsidyName),
            year: new Date().getFullYear(),
            totalAmount: 0
          };
        }
      }
    }
    
    var subsidies = Object.values(subsidiesMap);
    if (subsidies.length === 0) return 0;
    
    var existingSubsidies = {};
    var targetData = targetSheet.getDataRange().getValues();
    for (var i = 1; i < targetData.length; i++) {
      var existingName = targetData[i][1];
      if (existingName) {
        existingSubsidies[existingName.toString().trim()] = true;
      }
    }
    
    var newSubsidies = [];
    var lastRow = targetSheet.getLastRow();
    var startRow = lastRow === 1 ? 2 : lastRow + 1;
    var newId = lastRow;
    
    subsidies.forEach(function(subsidy) {
      if (!existingSubsidies[subsidy.name]) {
        newId++;
        newSubsidies.push([
          newId, subsidy.name, subsidy.shortName, subsidy.department,
          subsidy.year, subsidy.totalAmount, 0, 0, 0, 0, 0, 'Да'
        ]);
      }
    });
    
    if (newSubsidies.length > 0) {
      targetSheet.getRange(startRow, 1, newSubsidies.length, 12).setValues(newSubsidies);
    }
    
    return newSubsidies.length;
  } catch (error) {
    Logger.log('Ошибка при импорте субсидий: ' + error.message);
    return 0;
  }
}

function importCategoriesFEOFromSource(sourceSS, targetSS) {
  try {
    var sourceSheet = sourceSS.getSheetByName('Категории_из_ФЭО');
    if (!sourceSheet) {
      var sheets = sourceSS.getSheets();
      for (var i = 0; i < sheets.length; i++) {
        var sheetName = sheets[i].getName().toLowerCase();
        if (sheetName.indexOf('категории') !== -1 && (sheetName.indexOf('фео') !== -1 || sheetName.indexOf('feo') !== -1)) {
          sourceSheet = sheets[i];
          break;
        }
      }
    }
    if (!sourceSheet) return 0;
    
    var targetSheet = targetSS.getSheetByName('Категории_из_ФЭО');
    if (!targetSheet) return 0;
    
    var dataRange = sourceSheet.getDataRange();
    var values = dataRange.getValues();
    if (values.length < 2) return 0;
    
    if (targetSheet.getLastRow() > 1) {
      targetSheet.getRange(2, 1, targetSheet.getLastRow() - 1, targetSheet.getLastColumn()).clearContent();
    }
    
    var dataToInsert = values.slice(1);
    if (dataToInsert.length > 0) {
      targetSheet.getRange(2, 1, dataToInsert.length, dataToInsert[0].length).setValues(dataToInsert);
    }
    
    return dataToInsert.length;
  } catch (error) {
    Logger.log('Ошибка при импорте категорий ФЭО: ' + error.message);
    return 0;
  }
}

function importCategoriesAppFromSource(sourceSS, targetSS) {
  try {
    var sourceSheet = sourceSS.getSheetByName('Категории_из_приложения');
    
    if (!sourceSheet) {
      var sheets = sourceSS.getSheets();
      for (var i = 0; i < sheets.length; i++) {
        var sheetName = sheets[i].getName().toLowerCase();
        if (sheetName.indexOf('категории') !== -1 && sheetName.indexOf('приложения') !== -1) {
          sourceSheet = sheets[i];
          Logger.log('Найден лист: ' + sheets[i].getName());
          break;
        }
      }
    }
    
    if (!sourceSheet) {
      Logger.log('Лист с категориями из приложения не найден. Проверяю все листы...');
      var allSheets = sourceSS.getSheets();
      Logger.log('Доступные листы:');
      for (var i = 0; i < allSheets.length; i++) {
        Logger.log('- ' + allSheets[i].getName());
      }
      return 0;
    }
    
    var targetSheet = targetSS.getSheetByName('Категории_из_приложения');
    if (!targetSheet) {
      Logger.log('Целевой лист Категории_из_приложения не найден');
      return 0;
    }
    
    var dataRange = sourceSheet.getDataRange();
    var values = dataRange.getValues();
    
    Logger.log('Найдено строк в исходном файле: ' + values.length);
    
    if (values.length < 2) {
      Logger.log('Нет данных для импорта (только заголовки)');
      return 0;
    }
    
    if (targetSheet.getLastRow() > 1) {
      targetSheet.getRange(2, 1, targetSheet.getLastRow() - 1, targetSheet.getLastColumn()).clearContent();
    }
    
    var dataToInsert = values.slice(1);
    
    Logger.log('Данных для вставки: ' + dataToInsert.length + ' строк');
    
    if (dataToInsert.length > 0 && dataToInsert[0].length > 0) {
      var maxCols = Math.max(targetSheet.getLastColumn(), dataToInsert[0].length);
      targetSheet.getRange(2, 1, dataToInsert.length, maxCols).setValues(dataToInsert);
      Logger.log('Импортировано категорий из приложения: ' + dataToInsert.length + ' строк');
      
      // После импорта обновляем выпадающие списки
      setupInitialFEODropdowns(targetSS);
    }
    
    return dataToInsert.length;
  } catch (error) {
    Logger.log('Ошибка при импорте категорий из приложения: ' + error.message);
    Logger.log('Стек ошибки: ' + error.stack);
    return 0;
  }
}

function importContractorsFromSource(sourceSS, targetSS) {
  try {
    var sourceSheet = sourceSS.getSheetByName('GoodsService');
    if (!sourceSheet) return 0;
    
    var targetSheet = targetSS.getSheetByName('Контрагенты');
    if (!targetSheet) return 0;
    
    var dataRange = sourceSheet.getDataRange();
    var values = dataRange.getValues();
    if (values.length < 2) return 0;
    
    var headers = values[0];
    var contractorColumnIndex = -1;
    var possibleNames = ['контрагент', 'contractor', 'поставщик', 'исполнитель', 'подрядчик'];
    
    for (var i = 0; i < headers.length; i++) {
      var header = headers[i].toString().toLowerCase();
      for (var j = 0; j < possibleNames.length; j++) {
        if (header.indexOf(possibleNames[j]) !== -1) {
          contractorColumnIndex = i;
          break;
        }
      }
      if (contractorColumnIndex !== -1) break;
    }
    
    if (contractorColumnIndex === -1) return 0;
    
    var contractorsMap = {};
    for (var i = 1; i < values.length; i++) {
      var contractorValue = values[i][contractorColumnIndex];
      if (contractorValue && contractorValue.toString().trim() !== '') {
        var contractorName = contractorValue.toString().trim();
        if (!contractorsMap[contractorName]) {
          contractorsMap[contractorName] = { name: contractorName, fullName: contractorName };
        }
      }
    }
    
    var contractors = Object.values(contractorsMap);
    if (contractors.length === 0) return 0;
    
    var existingContractors = {};
    var targetData = targetSheet.getDataRange().getValues();
    for (var i = 1; i < targetData.length; i++) {
      var existingName = targetData[i][1];
      if (existingName) {
        existingContractors[existingName.toString().trim()] = true;
      }
    }
    
    var newContractors = [];
    var lastRow = targetSheet.getLastRow();
    var startRow = lastRow === 1 ? 2 : lastRow + 1;
    var newId = lastRow;
    
    contractors.forEach(function(contractor) {
      if (!existingContractors[contractor.name]) {
        newId++;
        var row = [newId, contractor.name, contractor.fullName, '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', new Date(), new Date(), 'Да'];
        newContractors.push(row);
      }
    });
    
    if (newContractors.length > 0) {
      targetSheet.getRange(startRow, 1, newContractors.length, 33).setValues(newContractors);
    }
    
    return newContractors.length;
  } catch (error) {
    Logger.log('Ошибка при импорте контрагентов: ' + error.message);
    return 0;
  }
}

function determineDepartment(subsidyName) {
  var name = subsidyName.toLowerCase();
  if (name.indexOf('минпрос') !== -1 || name.indexOf('просвещ') !== -1) return 'Минпрос';
  if (name.indexOf('минтруд') !== -1 || name.indexOf('труд') !== -1) return 'Минтруд';
  if (name.indexOf('фадм') !== -1) return 'ФАДМ';
  if (name.indexOf('регион') !== -1) return 'Регионы';
  return '';
}

function getShortName(fullName) {
  var words = fullName.split(' ');
  if (words.length > 3) {
    return words.slice(0, 3).join(' ');
  }
  return fullName;
}

// ============================================================================
// ДИАГНОСТИКА И ТЕСТИРОВАНИЕ
// ============================================================================

/**
 * Функция для диагностики и исправления проблем
 * Запускать для проверки работоспособности системы
 */
function testAndFix() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var results = {
    menu: false,
    sheets: [],
    files: [],
    errors: []
  };
  
  try {
    // 1. Создаем меню
    createMenu();
    results.menu = true;
    Logger.log('Меню создано');
  } catch (error) {
    results.errors.push('Ошибка создания меню: ' + error.message);
  }
  
  // 2. Проверяем структуру листов
  var requiredSheets = [
    'GoodsService', 'Состав_договора', 'Контрагенты', 'Субсидии',
    'Категории_из_ФЭО', 'Категории_из_приложения', 'Платежи',
    'Документы', 'Дашборд', 'Реестр_договоров'
  ];
  
  var existingSheets = [];
  var missingSheets = [];
  
  requiredSheets.forEach(function(sheetName) {
    var sheet = ss.getSheetByName(sheetName);
    if (sheet) {
      existingSheets.push(sheetName);
    } else {
      missingSheets.push(sheetName);
    }
  });
  
  results.sheets = {
    existing: existingSheets,
    missing: missingSheets,
    total: requiredSheets.length,
    found: existingSheets.length
  };
  
  // 3. Проверяем доступные файлы
  try {
    var files = getAvailableFiles();
    results.files = files;
    Logger.log('Найдено файлов: ' + files.length);
  } catch (error) {
    results.errors.push('Ошибка поиска файлов: ' + error.message);
  }
  
  // 4. Формируем сообщение
  var message = '🔍 ДИАГНОСТИКА СИСТЕМЫ\n\n';
  
  message += '✅ Меню: ' + (results.menu ? 'Создано' : 'Ошибка') + '\n\n';
  
  message += '📊 Листы: ' + results.sheets.found + ' из ' + results.sheets.total + '\n';
  if (results.sheets.missing.length > 0) {
    message += '❌ Отсутствуют: ' + results.sheets.missing.join(', ') + '\n';
    message += '\n💡 Запустите функцию createDatabaseStructure() для создания недостающих листов\n';
  } else {
    message += '✅ Все листы созданы\n';
  }
  
  message += '\n📁 Файлы для импорта: ' + results.files.length + '\n';
  if (results.files.length > 0) {
    message += '\nНайденные файлы:\n';
    results.files.slice(0, 5).forEach(function(file) {
      message += '  • ' + file.name + '\n';
    });
    if (results.files.length > 5) {
      message += '  ... и еще ' + (results.files.length - 5) + ' файлов\n';
    }
  } else {
    message += '⚠️ Файлы не найдены. Убедитесь, что файл "Патриотика" существует в Google Sheets\n';
  }
  
  if (results.errors.length > 0) {
    message += '\n❌ Ошибки:\n';
    results.errors.forEach(function(error) {
      message += '  • ' + error + '\n';
    });
  }
  
  message += '\n💡 РЕКОМЕНДАЦИИ:\n';
  if (results.sheets.missing.length > 0) {
    message += '1. Запустите createDatabaseStructure() для создания листов\n';
  }
  if (!results.menu) {
    message += '2. Запустите createMenu() для создания меню\n';
  }
  if (results.files.length === 0) {
    message += '3. Убедитесь, что файл "Патриотика" существует в Google Sheets\n';
  }
  message += '4. Обновите страницу Google Sheets (F5)\n';
  message += '5. Используйте меню "📥 Импорт данных" для импорта\n';
  
  // Показываем результаты
  SpreadsheetApp.getUi().alert('Диагностика системы', message, SpreadsheetApp.getUi().ButtonSet.OK);
  
  Logger.log('Диагностика завершена');
  Logger.log('Результаты: ' + JSON.stringify(results));
  
  return results;
}

/**
 * Быстрый импорт из текущего файла (если данные в том же файле)
 */
function quickImportFromCurrentFile() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var fileId = ss.getId();
  
  SpreadsheetApp.getUi().alert(
    'Импорт данных',
    'Начинаю импорт данных из текущего файла...\n\nПожалуйста, подождите.\n\nЭто может занять несколько секунд.',
    SpreadsheetApp.getUi().ButtonSet.OK
  );
  
  Logger.log('Начало импорта из файла ID: ' + fileId);
  
  var result = importDataFromFile(fileId);
  
  Logger.log('Результат импорта: ' + JSON.stringify(result));
  
  if (result.success) {
    var message = '✅ ИМПОРТ ЗАВЕРШЕН!\n\n';
    message += 'Результаты:\n';
    message += '• Субсидии: ' + result.results.subsidies + '\n';
    message += '• Категории ФЭО: ' + result.results.categoriesFEO + '\n';
    message += '• Категории из приложения: ' + result.results.categoriesApp + '\n';
    message += '• Контрагенты: ' + result.results.contractors + '\n\n';
    
    if (result.results.categoriesFEO > 0 || result.results.categoriesApp > 0) {
      message += '📋 ВАЖНО:\n';
      message += 'Обновите выпадающие списки ФЭО:\n';
      message += 'Меню → "🔄 Обновить выпадающие списки ФЭО"\n';
      message += 'Или запустите функцию updateFEODropdowns()';
    }
    
    SpreadsheetApp.getUi().alert('Успех!', message, SpreadsheetApp.getUi().ButtonSet.OK);
    
    // Автоматически обновляем выпадающие списки после импорта
    if (result.results.categoriesFEO > 0 || result.results.categoriesApp > 0) {
      try {
        setupInitialFEODropdowns(ss);
        Logger.log('Выпадающие списки обновлены автоматически');
      } catch (error) {
        Logger.log('Ошибка при автоматическом обновлении списков: ' + error.message);
      }
    }
  } else {
    var errorMsg = '❌ ОШИБКА ИМПОРТА\n\n' + result.message + '\n\n';
    errorMsg += 'Проверьте логи выполнения в Apps Script для подробностей.';
    SpreadsheetApp.getUi().alert('Ошибка', errorMsg, SpreadsheetApp.getUi().ButtonSet.OK);
  }
}

