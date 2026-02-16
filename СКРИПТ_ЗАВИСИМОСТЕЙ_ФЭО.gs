/**
 * Скрипт для настройки зависимостей категорий ФЭО
 * Обрабатывает изменения в столбцах категорий и обновляет зависимые списки
 */

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
    
    // Обрабатываем только лист GoodsService
    if (sheetName !== 'GoodsService') return;
    
    // Столбец AI (35) - Направление расходов ФЭО
    if (editedColumn === 35 && editedRow >= 2 && e.value) {
      updateFEOCategoryDependencies(sheet, editedRow, e.value, 'Категории_из_ФЭО', 36);
    }
    
    // Столбец AJ (36) - Тип расходов ФЭО
    if (editedColumn === 36 && editedRow >= 2 && e.value) {
      updateFEOCategoryDependencies(sheet, editedRow, e.value, 'Категории_из_ФЭО', 37);
    }
    
    // Столбец AK (37) - Направление из приложения
    if (editedColumn === 37 && editedRow >= 2 && e.value) {
      updateFEOCategoryDependencies(sheet, editedRow, e.value, 'Категории_из_приложения', 38);
    }
    
    // Столбец AL (38) - Тип конкретизированный
    if (editedColumn === 38 && editedRow >= 2 && e.value) {
      // Это последний уровень, ничего не делаем
    }
    
    // Очистка зависимых полей при изменении родительского
    if (editedColumn === 35 && editedRow >= 2) {
      // Очищаем AJ, AK, AL при изменении AI
      sheet.getRange(editedRow, 36).clearContent();
      sheet.getRange(editedRow, 37).clearContent();
      sheet.getRange(editedRow, 38).clearContent();
      sheet.getRange(editedRow, 36).removeDataValidation();
      sheet.getRange(editedRow, 37).removeDataValidation();
      sheet.getRange(editedRow, 38).removeDataValidation();
    }
    
    if (editedColumn === 36 && editedRow >= 2) {
      // Очищаем AK, AL при изменении AJ
      sheet.getRange(editedRow, 37).clearContent();
      sheet.getRange(editedRow, 38).clearContent();
      sheet.getRange(editedRow, 37).removeDataValidation();
      sheet.getRange(editedRow, 38).removeDataValidation();
    }
    
    if (editedColumn === 37 && editedRow >= 2) {
      // Очищаем AL при изменении AK
      sheet.getRange(editedRow, 38).clearContent();
      sheet.getRange(editedRow, 38).removeDataValidation();
    }
    
  } catch (error) {
    Logger.log('Ошибка в onEdit: ' + error.message);
  }
}

/**
 * Обновление зависимостей категорий ФЭО
 */
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
    
    // Ищем выбранное значение в первом столбце (категории)
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
    
    // Получаем подкатегории из строки categoryIndex
    var subcategories = [];
    for (var col = 1; col < categoryData[0].length; col++) {
      var subcategory = categoryData[categoryIndex][col];
      if (subcategory && subcategory.toString().trim() !== '') {
        subcategories.push(subcategory.toString().trim());
      }
    }
    
    // Устанавливаем выпадающий список для зависимого столбца
    var targetRange = sheet.getRange(row, targetColumn);
    
    if (subcategories.length > 0) {
      var rule = SpreadsheetApp.newDataValidation()
        .requireValueInList(subcategories)
        .setAllowInvalid(false)
        .build();
      targetRange.setDataValidation(rule);
      Logger.log('Установлен список из ' + subcategories.length + ' значений для строки ' + row);
    } else {
      targetRange.removeDataValidation();
      Logger.log('Нет подкатегорий для "' + selectedValue + '"');
    }
    
  } catch (error) {
    Logger.log('Ошибка при обновлении зависимостей: ' + error.message);
  }
}

/**
 * Инициализация зависимостей для всех строк в GoodsService
 * Запускать после создания структуры или при необходимости
 */
function initializeAllFEODependencies() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName('GoodsService');
  
  if (!sheet) {
    Logger.log('Лист GoodsService не найден');
    return;
  }
  
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return;
  
  // Обрабатываем каждую строку
  for (var row = 2; row <= lastRow; row++) {
    var aiValue = sheet.getRange(row, 35).getValue(); // AI - Направление расходов ФЭО
    var ajValue = sheet.getRange(row, 36).getValue(); // AJ - Тип расходов ФЭО
    var akValue = sheet.getRange(row, 37).getValue(); // AK - Направление из приложения
    
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
  
  Logger.log('Инициализация зависимостей завершена для ' + (lastRow - 1) + ' строк');
}

/**
 * Настройка зависимостей для состава договора
 * Аналогично для листа Состав_договора
 */
function onEditContractItems(e) {
  if (!e) return;
  
  try {
    var sheet = e.source.getActiveSheet();
    var sheetName = sheet.getName();
    var editedColumn = e.range.getColumn();
    var editedRow = e.range.getRow();
    
    // Обрабатываем только лист Состав_договора
    if (sheetName !== 'Состав_договора') return;
    
    // Столбец U (21) - Направление расходов ФЭО
    if (editedColumn === 21 && editedRow >= 2 && e.value) {
      updateFEOCategoryDependencies(sheet, editedRow, e.value, 'Категории_из_ФЭО', 22);
    }
    
    // Столбец V (22) - Тип расходов ФЭО
    if (editedColumn === 22 && editedRow >= 2 && e.value) {
      updateFEOCategoryDependencies(sheet, editedRow, e.value, 'Категории_из_ФЭО', 23);
    }
    
    // Столбец W (23) - Направление из приложения
    if (editedColumn === 23 && editedRow >= 2 && e.value) {
      updateFEOCategoryDependencies(sheet, editedRow, e.value, 'Категории_из_приложения', 24);
    }
    
  } catch (error) {
    Logger.log('Ошибка в onEditContractItems: ' + error.message);
  }
}



