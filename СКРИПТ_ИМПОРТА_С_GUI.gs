/**
 * Скрипт для импорта данных из Google Sheets файла
 * С GUI для выбора файла
 */

/**
 * Функция для создания меню при открытии таблицы
 */
function onOpen() {
  var ui = SpreadsheetApp.getUi();
  ui.createMenu('Импорт данных')
    .addItem('Импорт из Google Sheets файла', 'showFileSelectionDialog')
    .addSeparator()
    .addItem('Импорт из текущего файла', 'importFromCurrentFile')
    .addToUi();
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
        body {
          font-family: Arial, sans-serif;
          padding: 20px;
          background-color: #f5f5f5;
        }
        .container {
          background: white;
          padding: 20px;
          border-radius: 8px;
          box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h2 {
          margin-top: 0;
          color: #1a73e8;
        }
        .search-box {
          width: 100%;
          padding: 10px;
          margin-bottom: 15px;
          border: 1px solid #ddd;
          border-radius: 4px;
          box-sizing: border-box;
        }
        .file-list {
          max-height: 300px;
          overflow-y: auto;
          border: 1px solid #ddd;
          border-radius: 4px;
          margin-bottom: 15px;
        }
        .file-item {
          padding: 10px;
          cursor: pointer;
          border-bottom: 1px solid #eee;
          transition: background-color 0.2s;
        }
        .file-item:hover {
          background-color: #f0f0f0;
        }
        .file-item.selected {
          background-color: #e3f2fd;
          border-left: 3px solid #1a73e8;
        }
        .file-name {
          font-weight: bold;
          color: #333;
        }
        .file-info {
          font-size: 12px;
          color: #666;
          margin-top: 5px;
        }
        .button-group {
          text-align: right;
          margin-top: 20px;
        }
        button {
          padding: 10px 20px;
          margin-left: 10px;
          border: none;
          border-radius: 4px;
          cursor: pointer;
          font-size: 14px;
        }
        .btn-primary {
          background-color: #1a73e8;
          color: white;
        }
        .btn-primary:hover {
          background-color: #1557b0;
        }
        .btn-secondary {
          background-color: #5f6368;
          color: white;
        }
        .btn-secondary:hover {
          background-color: #3c4043;
        }
        .loading {
          text-align: center;
          padding: 20px;
          color: #666;
        }
        .error {
          color: #d32f2f;
          padding: 10px;
          background-color: #ffebee;
          border-radius: 4px;
          margin-bottom: 15px;
        }
        .success {
          color: #388e3c;
          padding: 10px;
          background-color: #e8f5e9;
          border-radius: 4px;
          margin-bottom: 15px;
        }
        #result {
          margin-top: 15px;
        }
      </style>
    </head>
    <body>
      <div class="container">
        <h2>Выбор файла для импорта</h2>
        
        <div id="errorMessage"></div>
        <div id="successMessage"></div>
        
        <input type="text" 
               id="searchBox" 
               class="search-box" 
               placeholder="Поиск файлов по названию..."
               onkeyup="filterFiles()">
        
        <div class="file-list" id="fileList">
          <div class="loading">Загрузка файлов...</div>
        </div>
        
        <div class="button-group">
          <button class="btn-secondary" onclick="google.script.host.close()">Отмена</button>
          <button class="btn-primary" onclick="importData()" id="importBtn" disabled>Импортировать</button>
        </div>
        
        <div id="result"></div>
      </div>
      
      <script>
        var selectedFileId = null;
        var files = [];
        
        // Загрузить список файлов при открытии
        window.onload = function() {
          loadFiles();
        };
        
        function loadFiles() {
          google.script.run
            .withSuccessHandler(function(fileList) {
              files = fileList;
              displayFiles(fileList);
            })
            .withFailureHandler(function(error) {
              document.getElementById('fileList').innerHTML = 
                '<div class="error">Ошибка загрузки файлов: ' + error.message + '</div>';
            })
            .getAvailableFiles();
        }
        
        function displayFiles(fileList) {
          var fileListDiv = document.getElementById('fileList');
          
          if (fileList.length === 0) {
            fileListDiv.innerHTML = '<div class="loading">Файлы не найдены</div>';
            return;
          }
          
          var html = '';
          fileList.forEach(function(file) {
            html += '<div class="file-item" onclick="selectFile(\'' + file.id + '\', this)" data-name="' + 
                    file.name.toLowerCase() + '">';
            html += '<div class="file-name">' + file.name + '</div>';
            html += '<div class="file-info">ID: ' + file.id + '</div>';
            html += '</div>';
          });
          
          fileListDiv.innerHTML = html;
        }
        
        function selectFile(fileId, element) {
          // Убираем выделение с других элементов
          var items = document.getElementsByClassName('file-item');
          for (var i = 0; i < items.length; i++) {
            items[i].classList.remove('selected');
          }
          
          // Выделяем выбранный элемент
          element.classList.add('selected');
          selectedFileId = fileId;
          
          // Активируем кнопку импорта
          document.getElementById('importBtn').disabled = false;
        }
        
        function filterFiles() {
          var searchText = document.getElementById('searchBox').value.toLowerCase();
          var items = document.getElementsByClassName('file-item');
          
          for (var i = 0; i < items.length; i++) {
            var fileName = items[i].getAttribute('data-name');
            if (fileName.indexOf(searchText) !== -1) {
              items[i].style.display = '';
            } else {
              items[i].style.display = 'none';
            }
          }
        }
        
        function importData() {
          if (!selectedFileId) {
            alert('Выберите файл для импорта!');
            return;
          }
          
          // Показываем загрузку
          document.getElementById('importBtn').disabled = true;
          document.getElementById('importBtn').textContent = 'Импорт...';
          document.getElementById('result').innerHTML = '<div class="loading">Импорт данных...</div>';
          
          google.script.run
            .withSuccessHandler(function(result) {
              document.getElementById('importBtn').disabled = false;
              document.getElementById('importBtn').textContent = 'Импортировать';
              
              if (result.success) {
                var resultHtml = '<div class="success">Импорт завершен успешно!</div>';
                resultHtml += '<div style="margin-top: 15px;">';
                resultHtml += '<p><strong>Результаты импорта:</strong></p>';
                resultHtml += '<ul>';
                resultHtml += '<li>Субсидии: ' + result.results.subsidies + '</li>';
                resultHtml += '<li>Категории ФЭО: ' + result.results.categoriesFEO + '</li>';
                resultHtml += '<li>Категории из приложения: ' + result.results.categoriesApp + '</li>';
                resultHtml += '<li>Контрагенты: ' + result.results.contractors + '</li>';
                resultHtml += '</ul>';
                resultHtml += '</div>';
                
                document.getElementById('result').innerHTML = resultHtml;
                
                // Закрываем диалог через 3 секунды
                setTimeout(function() {
                  google.script.host.close();
                }, 3000);
              } else {
                document.getElementById('result').innerHTML = 
                  '<div class="error">Ошибка: ' + result.message + '</div>';
              }
            })
            .withFailureHandler(function(error) {
              document.getElementById('importBtn').disabled = false;
              document.getElementById('importBtn').textContent = 'Импортировать';
              document.getElementById('result').innerHTML = 
                '<div class="error">Ошибка: ' + error.message + '</div>';
            })
            .importDataFromFile(selectedFileId);
        }
      </script>
    </body>
    </html>
  `)
    .setWidth(600)
    .setHeight(600)
    .setTitle('Импорт данных из Google Sheets');
  
  SpreadsheetApp.getUi().showModalDialog(html, 'Выбор файла для импорта');
}

/**
 * Получить список доступных файлов Google Sheets
 */
function getAvailableFiles() {
  try {
    var files = [];
    var searchTerms = ['Патриотика', 'патриотика', 'patriotika'];
    
    // Ищем файлы по ключевым словам
    searchTerms.forEach(function(term) {
      var fileIterator = DriveApp.getFilesByName(term);
      while (fileIterator.hasNext()) {
        var file = fileIterator.next();
        if (file.getMimeType() === MimeType.GOOGLE_SHEETS) {
          // Проверяем, не добавляли ли уже этот файл
          var alreadyAdded = files.some(function(f) {
            return f.id === file.getId();
          });
          
          if (!alreadyAdded) {
            files.push({
              id: file.getId(),
              name: file.getName(),
              url: file.getUrl()
            });
          }
        }
      }
    });
    
    // Также ищем файлы, содержащие "патриотика" в названии
    var allFiles = DriveApp.searchFiles('title contains "патриотика" and mimeType="application/vnd.google-apps.spreadsheet"');
    while (allFiles.hasNext()) {
      var file = allFiles.next();
      var alreadyAdded = files.some(function(f) {
        return f.id === file.getId();
      });
      
      if (!alreadyAdded) {
        files.push({
          id: file.getId(),
          name: file.getName(),
          url: file.getUrl()
        });
      }
    }
    
    // Если файлов не найдено, показываем последние 20 файлов Google Sheets
    if (files.length === 0) {
      var recentFiles = DriveApp.getFilesByType(MimeType.GOOGLE_SHEETS);
      var count = 0;
      while (recentFiles.hasNext() && count < 20) {
        var file = recentFiles.next();
        files.push({
          id: file.getId(),
          name: file.getName(),
          url: file.getUrl()
        });
        count++;
      }
    }
    
    // Сортируем по имени
    files.sort(function(a, b) {
      return a.name.localeCompare(b.name);
    });
    
    Logger.log('Найдено файлов: ' + files.length);
    return files;
    
  } catch (error) {
    Logger.log('Ошибка при получении списка файлов: ' + error.message);
    return [];
  }
}

/**
 * Импорт данных из выбранного файла
 */
function importDataFromFile(fileId) {
  try {
    var file = DriveApp.getFileById(fileId);
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    
    Logger.log('Начало импорта из файла: ' + file.getName() + ' (ID: ' + fileId + ')');
    
    // Открываем исходный файл
    var sourceSS = SpreadsheetApp.openById(fileId);
    
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
    
    Logger.log('Импорт завершен. Результаты: ' + JSON.stringify(results));
    
    return {
      success: true,
      message: 'Импорт завершен успешно',
      results: results
    };
    
  } catch (error) {
    Logger.log('Ошибка при импорте: ' + error.message);
    return {
      success: false,
      message: 'Ошибка: ' + error.message
    };
  }
}

/**
 * Импорт из текущего файла (если данные в том же файле)
 */
function importFromCurrentFile() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var fileId = ss.getId();
  
  var result = importDataFromFile(fileId);
  
  if (result.success) {
    SpreadsheetApp.getUi().alert(
      'Импорт завершен!',
      'Импортировано:\n' +
      'Субсидии: ' + result.results.subsidies + '\n' +
      'Категории ФЭО: ' + result.results.categoriesFEO + '\n' +
      'Категории из приложения: ' + result.results.categoriesApp + '\n' +
      'Контрагенты: ' + result.results.contractors,
      SpreadsheetApp.getUi().ButtonSet.OK
    );
  } else {
    SpreadsheetApp.getUi().alert('Ошибка', result.message, SpreadsheetApp.getUi().ButtonSet.OK);
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
    
    var dataRange = sourceSheet.getDataRange();
    var values = dataRange.getValues();
    
    if (values.length < 2) {
      return 0;
    }
    
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
    
    if (subsidyColumnIndex === -1) {
      Logger.log('Столбец с субсидиями не найден');
      return 0;
    }
    
    Logger.log('Найден столбец с субсидиями: ' + subsidyColumnIndex + ' (' + headers[subsidyColumnIndex] + ')');
    
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
        var row = [
          newId,
          subsidy.name,
          subsidy.shortName,
          subsidy.department,
          subsidy.year,
          subsidy.totalAmount,
          0, 0, 0, 0, 0,
          'Да'
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
    
    if (targetSheet.getLastRow() > 1) {
      targetSheet.getRange(2, 1, targetSheet.getLastRow() - 1, targetSheet.getLastColumn()).clearContent();
    }
    
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
        var row = [
          newId, contractor.name, contractor.fullName,
          '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', new Date(), new Date(), 'Да'
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
 * Вспомогательные функции
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

function getShortName(fullName) {
  var words = fullName.split(' ');
  if (words.length > 3) {
    return words.slice(0, 3).join(' ');
  }
  return fullName;
}



