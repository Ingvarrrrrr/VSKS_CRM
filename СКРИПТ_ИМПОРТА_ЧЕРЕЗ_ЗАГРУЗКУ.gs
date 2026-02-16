/**
 * Альтернативный скрипт для импорта данных
 * Использует загрузку файла через диалоговое окно
 */

/**
 * Функция для показа диалога загрузки файла
 */
function showImportDialog() {
  var html = HtmlService.createHtmlOutputFromFile('ImportDialog')
    .setWidth(600)
    .setHeight(400)
    .setTitle('Импорт данных из Excel');
  
  SpreadsheetApp.getUi().showModalDialog(html, 'Импорт данных');
}

/**
 * Импорт данных из загруженного файла
 */
function importDataFromUploadedFile(fileId) {
  try {
    var file = DriveApp.getFileById(fileId);
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    
    Logger.log('Начало импорта из файла: ' + file.getName());
    
    // Конвертируем в Google Sheets формат
    var convertedFile = convertExcelToSheets(file);
    if (!convertedFile) {
      return {success: false, message: 'Не удалось конвертировать файл'};
    }
    
    var sourceSS = SpreadsheetApp.open(convertedFile);
    
    // Импорт данных
    var results = {
      subsidies: 0,
      categoriesFEO: 0,
      categoriesApp: 0,
      contractors: 0
    };
    
    // Импорт субсидий
    results.subsidies = importSubsidiesFromSource(sourceSS, ss);
    
    // Импорт категорий ФЭО
    results.categoriesFEO = importCategoriesFEOFromSource(sourceSS, ss);
    
    // Импорт категорий из приложения
    results.categoriesApp = importCategoriesAppFromSource(sourceSS, ss);
    
    // Импорт контрагентов
    results.contractors = importContractorsFromSource(sourceSS, ss);
    
    // Удаляем временный файл
    convertedFile.setTrashed(true);
    
    return {
      success: true,
      message: 'Импорт завершен успешно',
      results: results
    };
    
  } catch (error) {
    Logger.log('Ошибка при импорте: ' + error.message);
    return {success: false, message: 'Ошибка: ' + error.message};
  }
}

/**
 * Импорт субсидий из исходного файла
 */
function importSubsidiesFromSource(sourceSS, targetSS) {
  try {
    var sourceSheet = sourceSS.getSheetByName('GoodsService');
    if (!sourceSheet) {
      Logger.log('Лист GoodsService не найден в исходном файле');
      return 0;
    }
    
    var targetSheet = targetSS.getSheetByName('Субсидии');
    if (!targetSheet) {
      Logger.log('Лист Субсидии не найден в целевом файле');
      return 0;
    }
    
    // Получаем все данные из GoodsService
    var dataRange = sourceSheet.getDataRange();
    var values = dataRange.getValues();
    
    if (values.length < 2) {
      return 0;
    }
    
    // Ищем столбец с субсидиями (анализируем заголовки)
    var headers = values[0];
    var subsidyColumnIndex = -1;
    
    // Пробуем разные варианты названий столбцов
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
    
    if (subsidyColumnIndex === -1) {
      Logger.log('Столбец с субсидиями не найден. Анализируем все столбцы...');
      // Выводим все заголовки для отладки
      Logger.log('Заголовки: ' + headers.join(', '));
      return 0;
    }
    
    Logger.log('Найден столбец с субсидиями: ' + subsidyColumnIndex + ' (' + headers[subsidyColumnIndex] + ')');
    
    // Извлекаем уникальные субсидии
    var subsidiesMap = {};
    for (var i = 1; i < values.length; i++) {
      var subsidyValue = values[i][subsidyColumnIndex];
      if (subsidyValue && subsidyValue.toString().trim() !== '') {
        var subsidyName = subsidyValue.toString().trim();
        if (!subsidiesMap[subsidyName]) {
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
    
    var subsidies = Object.values(subsidiesMap);
    
    if (subsidies.length === 0) {
      Logger.log('Не найдено субсидий для импорта');
      return 0;
    }
    
    // Проверяем, какие субсидии уже есть
    var existingSubsidies = {};
    var targetData = targetSheet.getDataRange().getValues();
    for (var i = 1; i < targetData.length; i++) {
      var existingName = targetData[i][1]; // Столбец B - Наименование
      if (existingName) {
        existingSubsidies[existingName.toString().trim()] = true;
      }
    }
    
    // Добавляем только новые субсидии
    var newSubsidies = [];
    var lastRow = targetSheet.getLastRow();
    var startRow = lastRow === 1 ? 2 : lastRow + 1;
    var newId = lastRow;
    
    subsidies.forEach(function(subsidy) {
      if (!existingSubsidies[subsidy.name]) {
        newId++;
        var row = [
          newId, // ID
          subsidy.name, // Наименование
          subsidy.shortName, // Краткое наименование
          subsidy.department, // Ведомство
          subsidy.year, // Год
          subsidy.totalAmount, // Общий объём
          0, // Законтрактовано
          0, // Планируется
          0, // Поставлено
          0, // Оплачено
          0, // Остаток
          'Да' // Активна
        ];
        newSubsidies.push(row);
      }
    });
    
    if (newSubsidies.length > 0) {
      targetSheet.getRange(startRow, 1, newSubsidies.length, newSubsidies[0].length).setValues(newSubsidies);
      Logger.log('Импортировано новых субсидий: ' + newSubsidies.length);
    }
    
    return newSubsidies.length;
    
  } catch (error) {
    Logger.log('Ошибка при импорте субсидий: ' + error.message);
    return 0;
  }
}

/**
 * Импорт категорий ФЭО из исходного файла
 */
function importCategoriesFEOFromSource(sourceSS, targetSS) {
  try {
    // Ищем лист с категориями ФЭО
    var sourceSheet = sourceSS.getSheetByName('Категории_из_ФЭО');
    
    if (!sourceSheet) {
      // Пробуем найти похожий лист
      var sheets = sourceSS.getSheets();
      for (var i = 0; i < sheets.length; i++) {
        var sheetName = sheets[i].getName().toLowerCase();
        if (sheetName.indexOf('категории') !== -1 && (sheetName.indexOf('фео') !== -1 || sheetName.indexOf('feo') !== -1)) {
          sourceSheet = sheets[i];
          break;
        }
      }
    }
    
    if (!sourceSheet) {
      Logger.log('Лист с категориями ФЭО не найден');
      return 0;
    }
    
    var targetSheet = targetSS.getSheetByName('Категории_из_ФЭО');
    if (!targetSheet) {
      return 0;
    }
    
    var dataRange = sourceSheet.getDataRange();
    var values = dataRange.getValues();
    
    if (values.length < 2) {
      return 0;
    }
    
    // Очищаем целевой лист (кроме заголовков)
    if (targetSheet.getLastRow() > 1) {
      targetSheet.getRange(2, 1, targetSheet.getLastRow() - 1, targetSheet.getLastColumn()).clearContent();
    }
    
    // Копируем данные начиная со второй строки
    var dataToInsert = values.slice(1);
    
    if (dataToInsert.length > 0) {
      targetSheet.getRange(2, 1, dataToInsert.length, dataToInsert[0].length).setValues(dataToInsert);
      Logger.log('Импортировано категорий ФЭО: ' + dataToInsert.length);
    }
    
    return dataToInsert.length;
    
  } catch (error) {
    Logger.log('Ошибка при импорте категорий ФЭО: ' + error.message);
    return 0;
  }
}

/**
 * Импорт категорий из приложения
 */
function importCategoriesAppFromSource(sourceSS, targetSS) {
  try {
    var sourceSheet = sourceSS.getSheetByName('Категории_из_приложения');
    
    if (!sourceSheet) {
      var sheets = sourceSS.getSheets();
      for (var i = 0; i < sheets.length; i++) {
        var sheetName = sheets[i].getName().toLowerCase();
        if (sheetName.indexOf('категории') !== -1 && sheetName.indexOf('приложения') !== -1) {
          sourceSheet = sheets[i];
          break;
        }
      }
    }
    
    if (!sourceSheet) {
      Logger.log('Лист с категориями из приложения не найден');
      return 0;
    }
    
    var targetSheet = targetSS.getSheetByName('Категории_из_приложения');
    if (!targetSheet) {
      return 0;
    }
    
    var dataRange = sourceSheet.getDataRange();
    var values = dataRange.getValues();
    
    if (values.length < 2) {
      return 0;
    }
    
    if (targetSheet.getLastRow() > 1) {
      targetSheet.getRange(2, 1, targetSheet.getLastRow() - 1, targetSheet.getLastColumn()).clearContent();
    }
    
    var dataToInsert = values.slice(1);
    
    if (dataToInsert.length > 0) {
      targetSheet.getRange(2, 1, dataToInsert.length, dataToInsert[0].length).setValues(dataToInsert);
      Logger.log('Импортировано категорий из приложения: ' + dataToInsert.length);
    }
    
    return dataToInsert.length;
    
  } catch (error) {
    Logger.log('Ошибка при импорте категорий из приложения: ' + error.message);
    return 0;
  }
}

/**
 * Импорт контрагентов из исходного файла
 */
function importContractorsFromSource(sourceSS, targetSS) {
  try {
    var sourceSheet = sourceSS.getSheetByName('GoodsService');
    if (!sourceSheet) {
      return 0;
    }
    
    var targetSheet = targetSS.getSheetByName('Контрагенты');
    if (!targetSheet) {
      return 0;
    }
    
    var dataRange = sourceSheet.getDataRange();
    var values = dataRange.getValues();
    
    if (values.length < 2) {
      return 0;
    }
    
    // Ищем столбец с контрагентами
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
    
    if (contractorColumnIndex === -1) {
      Logger.log('Столбец с контрагентами не найден');
      return 0;
    }
    
    Logger.log('Найден столбец с контрагентами: ' + contractorColumnIndex + ' (' + headers[contractorColumnIndex] + ')');
    
    // Извлекаем уникальных контрагентов
    var contractorsMap = {};
    for (var i = 1; i < values.length; i++) {
      var contractorValue = values[i][contractorColumnIndex];
      if (contractorValue && contractorValue.toString().trim() !== '') {
        var contractorName = contractorValue.toString().trim();
        if (!contractorsMap[contractorName]) {
          contractorsMap[contractorName] = {
            name: contractorName,
            fullName: contractorName
          };
        }
      }
    }
    
    var contractors = Object.values(contractorsMap);
    
    if (contractors.length === 0) {
      return 0;
    }
    
    // Проверяем существующих контрагентов
    var existingContractors = {};
    var targetData = targetSheet.getDataRange().getValues();
    for (var i = 1; i < targetData.length; i++) {
      var existingName = targetData[i][1]; // Столбец B - Контрагент
      if (existingName) {
        existingContractors[existingName.toString().trim()] = true;
      }
    }
    
    // Добавляем только новых контрагентов
    var newContractors = [];
    var lastRow = targetSheet.getLastRow();
    var startRow = lastRow === 1 ? 2 : lastRow + 1;
    var newId = lastRow;
    
    contractors.forEach(function(contractor) {
      if (!existingContractors[contractor.name]) {
        newId++;
        var row = [
          newId, // ID
          contractor.name, // Контрагент
          contractor.fullName, // Полное наименование
          '', // ИНН
          '', // КПП
          '', // ОГРН
          '', // ОКПО
          '', // ОКТМО
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
        newContractors.push(row);
      }
    });
    
    if (newContractors.length > 0) {
      targetSheet.getRange(startRow, 1, newContractors.length, newContractors[0].length).setValues(newContractors);
      Logger.log('Импортировано новых контрагентов: ' + newContractors.length);
    }
    
    return newContractors.length;
    
  } catch (error) {
    Logger.log('Ошибка при импорте контрагентов: ' + error.message);
    return 0;
  }
}

/**
 * Вспомогательные функции (из предыдущего скрипта)
 */
function convertExcelToSheets(excelFile) {
  try {
    if (excelFile.getMimeType() === MimeType.GOOGLE_SHEETS) {
      return excelFile;
    }
    
    var blob = excelFile.getBlob();
    var convertedFile = DriveApp.createFile(blob.setName(excelFile.getName() + '_converted_' + new Date().getTime()));
    
    return convertedFile;
  } catch (error) {
    Logger.log('Ошибка при конвертации файла: ' + error.message);
    return null;
  }
}

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

function getShortName(fullName) {
  var words = fullName.split(' ');
  if (words.length > 3) {
    return words.slice(0, 3).join(' ');
  }
  return fullName;
}



