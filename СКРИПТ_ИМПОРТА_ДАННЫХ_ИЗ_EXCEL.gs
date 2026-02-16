/**
 * Скрипт для импорта данных из Excel файла в справочники
 * Автоматически заполняет справочники данными из файла "Патриотика 2025 (5).xlsx"
 */

/**
 * Основная функция импорта данных
 * Запускать после создания структуры БД
 */
function importDataFromExcel() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  
  Logger.log('Начало импорта данных...');
  
  // Импорт субсидий
  importSubsidies(ss);
  
  // Импорт категорий ФЭО
  importCategoriesFEO(ss);
  
  // Импорт категорий из приложения
  importCategoriesApp(ss);
  
  // Импорт контрагентов (если есть в файле)
  importContractors(ss);
  
  Logger.log('Импорт данных завершен!');
  
  SpreadsheetApp.getUi().alert('Импорт завершен', 'Данные успешно импортированы из Excel файла', SpreadsheetApp.getUi().ButtonSet.OK);
}

/**
 * Импорт субсидий из Excel файла
 * Ищет данные в листе "Субсидии" или определяет по данным в GoodsService
 */
function importSubsidies(ss) {
  try {
    // Пробуем найти файл Excel в Google Drive
    var excelFile = findExcelFile('Патриотика 2025 (5).xlsx');
    
    if (!excelFile) {
      Logger.log('Excel файл не найден в Google Drive. Необходимо загрузить файл в Google Drive.');
      return;
    }
    
    // Конвертируем Excel в Google Sheets формат (если нужно)
    var sheet = getOrCreateSheet(ss, 'Субсидии');
    
    // Извлекаем уникальные субсидии из листа GoodsService Excel файла
    var subsidiesData = extractSubsidiesFromExcel(excelFile);
    
    if (subsidiesData.length === 0) {
      Logger.log('Данные о субсидиях не найдены в Excel файле');
      return;
    }
    
    // Заполняем лист Субсидии
    var lastRow = sheet.getLastRow();
    var startRow = lastRow + 1;
    
    // Если лист пустой (только заголовки), начинаем с строки 2
    if (lastRow === 1) {
      startRow = 2;
    }
    
    var dataToInsert = [];
    subsidiesData.forEach(function(subsidy, index) {
      var row = [
        lastRow + index, // ID (автоинкремент)
        subsidy.name || '', // Наименование
        subsidy.shortName || subsidy.name || '', // Краткое наименование
        subsidy.department || '', // Ведомство
        subsidy.year || new Date().getFullYear(), // Год
        subsidy.totalAmount || 0, // Общий объём
        0, // Законтрактовано (будет рассчитано формулой)
        0, // Планируется (будет рассчитано формулой)
        0, // Поставлено (будет рассчитано формулой)
        0, // Оплачено (будет рассчитано формулой)
        0, // Остаток (будет рассчитано формулой)
        'Да' // Активна
      ];
      dataToInsert.push(row);
    });
    
    if (dataToInsert.length > 0) {
      sheet.getRange(startRow, 1, dataToInsert.length, dataToInsert[0].length).setValues(dataToInsert);
      Logger.log('Импортировано субсидий: ' + dataToInsert.length);
    }
    
  } catch (error) {
    Logger.log('Ошибка при импорте субсидий: ' + error.message);
  }
}

/**
 * Импорт категорий ФЭО из Excel файла
 */
function importCategoriesFEO(ss) {
  try {
    var excelFile = findExcelFile('Патриотика 2025 (5).xlsx');
    
    if (!excelFile) {
      Logger.log('Excel файл не найден');
      return;
    }
    
    var sheet = getOrCreateSheet(ss, 'Категории_из_ФЭО');
    
    // Извлекаем данные из листа "Категории_из_ФЭО" или определяем по структуре
    var categoriesData = extractCategoriesFEOFromExcel(excelFile);
    
    if (categoriesData.length === 0) {
      Logger.log('Данные о категориях ФЭО не найдены');
      return;
    }
    
    // Очищаем лист (кроме заголовков)
    if (sheet.getLastRow() > 1) {
      sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).clearContent();
    }
    
    // Заполняем данными
    var dataToInsert = [];
    categoriesData.forEach(function(category) {
      dataToInsert.push(category);
    });
    
    if (dataToInsert.length > 0) {
      sheet.getRange(2, 1, dataToInsert.length, dataToInsert[0].length).setValues(dataToInsert);
      Logger.log('Импортировано категорий ФЭО: ' + dataToInsert.length);
    }
    
  } catch (error) {
    Logger.log('Ошибка при импорте категорий ФЭО: ' + error.message);
  }
}

/**
 * Импорт категорий из приложения
 */
function importCategoriesApp(ss) {
  try {
    var excelFile = findExcelFile('Патриотика 2025 (5).xlsx');
    
    if (!excelFile) {
      Logger.log('Excel файл не найден');
      return;
    }
    
    var sheet = getOrCreateSheet(ss, 'Категории_из_приложения');
    
    var categoriesData = extractCategoriesAppFromExcel(excelFile);
    
    if (categoriesData.length === 0) {
      Logger.log('Данные о категориях из приложения не найдены');
      return;
    }
    
    // Очищаем лист (кроме заголовков)
    if (sheet.getLastRow() > 1) {
      sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).clearContent();
    }
    
    var dataToInsert = [];
    categoriesData.forEach(function(category) {
      dataToInsert.push(category);
    });
    
    if (dataToInsert.length > 0) {
      sheet.getRange(2, 1, dataToInsert.length, dataToInsert[0].length).setValues(dataToInsert);
      Logger.log('Импортировано категорий из приложения: ' + dataToInsert.length);
    }
    
  } catch (error) {
    Logger.log('Ошибка при импорте категорий из приложения: ' + error.message);
  }
}

/**
 * Импорт контрагентов (если есть в файле)
 */
function importContractors(ss) {
  try {
    var excelFile = findExcelFile('Патриотика 2025 (5).xlsx');
    
    if (!excelFile) {
      Logger.log('Excel файл не найден');
      return;
    }
    
    // Извлекаем уникальных контрагентов из GoodsService
    var contractorsData = extractContractorsFromExcel(excelFile);
    
    if (contractorsData.length === 0) {
      Logger.log('Данные о контрагентах не найдены');
      return;
    }
    
    var sheet = getOrCreateSheet(ss, 'Контрагенты');
    var lastRow = sheet.getLastRow();
    var startRow = lastRow === 1 ? 2 : lastRow + 1;
    
    var dataToInsert = [];
    contractorsData.forEach(function(contractor, index) {
      var row = [
        lastRow + index, // ID
        contractor.name || '', // Контрагент
        contractor.fullName || contractor.name || '', // Полное наименование
        contractor.inn || '', // ИНН
        contractor.kpp || '', // КПП
        contractor.ogrn || '', // ОГРН
        contractor.okpo || '', // ОКПО
        contractor.oktmo || '', // ОКТМО
        '', // ФИО руководителя
        '', // Должность руководителя
        '', // Основание действия
        '', // Номер доверенности
        '', // Дата доверенности
        '', // Кем выдана доверенность
        '', // Расчётный счёт
        '', // Кореспондентский счёт
        '', // БИК банка
        '', // Наименование банка
        '', // Юридический адрес
        '', // Почтовый адрес
        '', // Фактический адрес
        '', // Телефон организации
        '', // Факс
        '', // E-mail организации
        '', // Веб-сайт
        '', // Контактное лицо
        '', // Должность контактного лица
        '', // Телефон контактного лица
        '', // E-mail контактного лица
        '', // Дополнительные контакты
        new Date(), // Дата создания
        new Date(), // Дата изменения
        'Да' // Активен
      ];
      dataToInsert.push(row);
    });
    
    if (dataToInsert.length > 0) {
      sheet.getRange(startRow, 1, dataToInsert.length, dataToInsert[0].length).setValues(dataToInsert);
      Logger.log('Импортировано контрагентов: ' + dataToInsert.length);
    }
    
  } catch (error) {
    Logger.log('Ошибка при импорте контрагентов: ' + error.message);
  }
}

/**
 * Поиск Excel файла в Google Drive
 */
function findExcelFile(fileName) {
  try {
    var files = DriveApp.getFilesByName(fileName);
    if (files.hasNext()) {
      return files.next();
    }
    
    // Пробуем найти похожие файлы
    var allFiles = DriveApp.getFiles();
    while (allFiles.hasNext()) {
      var file = allFiles.next();
      if (file.getName().indexOf('Патриотика') !== -1 && file.getName().indexOf('.xlsx') !== -1) {
        return file;
      }
    }
    
    return null;
  } catch (error) {
    Logger.log('Ошибка при поиске файла: ' + error.message);
    return null;
  }
}

/**
 * Извлечение данных о субсидиях из Excel файла
 * Анализирует лист GoodsService и определяет уникальные субсидии
 */
function extractSubsidiesFromExcel(excelFile) {
  try {
    // Конвертируем Excel в Google Sheets (если нужно)
    var convertedFile = convertExcelToSheets(excelFile);
    if (!convertedFile) {
      Logger.log('Не удалось конвертировать Excel файл');
      return [];
    }
    
    var ss = SpreadsheetApp.open(convertedFile);
    var goodsServiceSheet = ss.getSheetByName('GoodsService');
    
    if (!goodsServiceSheet) {
      Logger.log('Лист GoodsService не найден');
      return [];
    }
    
    // Определяем столбец с субсидиями (нужно проанализировать структуру)
    // Предполагаем, что субсидия может быть в разных столбцах
    var dataRange = goodsServiceSheet.getDataRange();
    var values = dataRange.getValues();
    
    if (values.length < 2) {
      return [];
    }
    
    // Ищем столбец с субсидиями (анализируем заголовки)
    var subsidyColumnIndex = findColumnIndex(values[0], ['субсидия', 'subsidy', 'ведомство', 'department']);
    
    if (subsidyColumnIndex === -1) {
      Logger.log('Столбец с субсидиями не найден');
      return [];
    }
    
    // Извлекаем уникальные субсидии
    var subsidiesMap = {};
    for (var i = 1; i < values.length; i++) {
      var subsidyValue = values[i][subsidyColumnIndex];
      if (subsidyValue && subsidyValue.toString().trim() !== '') {
        var subsidyName = subsidyValue.toString().trim();
        if (!subsidiesMap[subsidyName]) {
          // Определяем ведомство по названию субсидии
          var department = determineDepartment(subsidyName);
          
          subsidiesMap[subsidyName] = {
            name: subsidyName,
            shortName: getShortName(subsidyName),
            department: department,
            year: new Date().getFullYear(),
            totalAmount: 0
          };
        }
      }
    }
    
    return Object.values(subsidiesMap);
    
  } catch (error) {
    Logger.log('Ошибка при извлечении субсидий: ' + error.message);
    return [];
  }
}

/**
 * Извлечение категорий ФЭО из Excel файла
 */
function extractCategoriesFEOFromExcel(excelFile) {
  try {
    var convertedFile = convertExcelToSheets(excelFile);
    if (!convertedFile) {
      return [];
    }
    
    var ss = SpreadsheetApp.open(convertedFile);
    
    // Ищем лист с категориями ФЭО
    var categorySheet = ss.getSheetByName('Категории_из_ФЭО');
    
    if (!categorySheet) {
      // Пробуем найти похожий лист
      var sheets = ss.getSheets();
      for (var i = 0; i < sheets.length; i++) {
        var sheetName = sheets[i].getName().toLowerCase();
        if (sheetName.indexOf('категории') !== -1 && sheetName.indexOf('фео') !== -1) {
          categorySheet = sheets[i];
          break;
        }
      }
    }
    
    if (!categorySheet) {
      Logger.log('Лист с категориями ФЭО не найден');
      return [];
    }
    
    var dataRange = categorySheet.getDataRange();
    var values = dataRange.getValues();
    
    if (values.length < 2) {
      return [];
    }
    
    // Возвращаем данные начиная со второй строки
    return values.slice(1);
    
  } catch (error) {
    Logger.log('Ошибка при извлечении категорий ФЭО: ' + error.message);
    return [];
  }
}

/**
 * Извлечение категорий из приложения
 */
function extractCategoriesAppFromExcel(excelFile) {
  try {
    var convertedFile = convertExcelToSheets(excelFile);
    if (!convertedFile) {
      return [];
    }
    
    var ss = SpreadsheetApp.open(convertedFile);
    
    var categorySheet = ss.getSheetByName('Категории_из_приложения');
    
    if (!categorySheet) {
      var sheets = ss.getSheets();
      for (var i = 0; i < sheets.length; i++) {
        var sheetName = sheets[i].getName().toLowerCase();
        if (sheetName.indexOf('категории') !== -1 && sheetName.indexOf('приложения') !== -1) {
          categorySheet = sheets[i];
          break;
        }
      }
    }
    
    if (!categorySheet) {
      Logger.log('Лист с категориями из приложения не найден');
      return [];
    }
    
    var dataRange = categorySheet.getDataRange();
    var values = dataRange.getValues();
    
    if (values.length < 2) {
      return [];
    }
    
    return values.slice(1);
    
  } catch (error) {
    Logger.log('Ошибка при извлечении категорий из приложения: ' + error.message);
    return [];
  }
}

/**
 * Извлечение контрагентов из Excel файла
 */
function extractContractorsFromExcel(excelFile) {
  try {
    var convertedFile = convertExcelToSheets(excelFile);
    if (!convertedFile) {
      return [];
    }
    
    var ss = SpreadsheetApp.open(convertedFile);
    var goodsServiceSheet = ss.getSheetByName('GoodsService');
    
    if (!goodsServiceSheet) {
      return [];
    }
    
    var dataRange = goodsServiceSheet.getDataRange();
    var values = dataRange.getValues();
    
    if (values.length < 2) {
      return [];
    }
    
    // Ищем столбец с контрагентами
    var contractorColumnIndex = findColumnIndex(values[0], ['контрагент', 'contractor', 'поставщик', 'исполнитель']);
    
    if (contractorColumnIndex === -1) {
      Logger.log('Столбец с контрагентами не найден');
      return [];
    }
    
    // Извлекаем уникальных контрагентов
    var contractorsMap = {};
    for (var i = 1; i < values.length; i++) {
      var contractorValue = values[i][contractorColumnIndex];
      if (contractorValue && contractorValue.toString().trim() !== '') {
        var contractorName = contractorValue.toString().trim();
        if (!contractorsMap[contractorName]) {
          contractorsMap[contractorName] = {
            name: contractorName,
            fullName: contractorName,
            inn: '',
            kpp: '',
            ogrn: '',
            okpo: '',
            oktmo: ''
          };
        }
      }
    }
    
    return Object.values(contractorsMap);
    
  } catch (error) {
    Logger.log('Ошибка при извлечении контрагентов: ' + error.message);
    return [];
  }
}

/**
 * Конвертация Excel файла в Google Sheets формат
 */
function convertExcelToSheets(excelFile) {
  try {
    // Если файл уже в формате Google Sheets, возвращаем его
    if (excelFile.getMimeType() === MimeType.GOOGLE_SHEETS) {
      return excelFile;
    }
    
    // Конвертируем Excel в Google Sheets
    var blob = excelFile.getBlob();
    var convertedFile = DriveApp.createFile(blob.setName(excelFile.getName() + '_converted'));
    
    // Удаляем временный файл после использования (опционально)
    // convertedFile.setTrashed(true);
    
    return convertedFile;
    
  } catch (error) {
    Logger.log('Ошибка при конвертации файла: ' + error.message);
    return null;
  }
}

/**
 * Поиск индекса столбца по ключевым словам
 */
function findColumnIndex(headers, keywords) {
  for (var i = 0; i < headers.length; i++) {
    var header = headers[i].toString().toLowerCase();
    for (var j = 0; j < keywords.length; j++) {
      if (header.indexOf(keywords[j].toLowerCase()) !== -1) {
        return i;
      }
    }
  }
  return -1;
}

/**
 * Определение ведомства по названию субсидии
 */
function determineDepartment(subsidyName) {
  var name = subsidyName.toLowerCase();
  if (name.indexOf('минпрос') !== -1 || name.indexOf('просвещ') !== -1) {
    return 'Минпрос';
  }
  if (name.indexOf('минтруд') !== -1 || name.indexOf('труд') !== -1) {
    return 'Минтруд';
  }
  if (name.indexOf('фадм') !== -1) {
    return 'ФАДМ';
  }
  if (name.indexOf('регион') !== -1) {
    return 'Регионы';
  }
  return '';
}

/**
 * Получение короткого названия субсидии
 */
function getShortName(fullName) {
  // Простая логика: берем первые слова или сокращаем
  var words = fullName.split(' ');
  if (words.length > 3) {
    return words.slice(0, 3).join(' ');
  }
  return fullName;
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



