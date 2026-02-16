@echo off
chcp 65001 >nul
echo ========================================
echo   CRM Система - Управление договорами
echo ========================================
echo.

REM Проверка наличия Python
py --version >nul 2>&1
if errorlevel 1 (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo [ОШИБКА] Python не установлен!
        echo Установите Python 3.8 или выше с https://www.python.org/
        pause
        exit /b 1
    )
    set PYTHON_CMD=python
) else (
    set PYTHON_CMD=py
)

REM Проверка зависимостей
echo [ИНФО] Проверка зависимостей...
%PYTHON_CMD% check_dependencies.py
if errorlevel 1 (
    echo [ОШИБКА] Проблемы с зависимостями
    pause
    exit /b 1
)

REM Проверка наличия файла базы данных
if not exist "CRM_База_Данных.xlsx" (
    echo [ИНФО] Файл базы данных не найден. Создаю структуру...
    %PYTHON_CMD% create_excel_structure.py
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать структуру базы данных
        pause
        exit /b 1
    )
    echo [УСПЕХ] Структура базы данных создана!
    echo.
)

REM Запуск приложения
echo [ИНФО] Запуск приложения...
echo.
%PYTHON_CMD% main.py

if errorlevel 1 (
    echo.
    echo [ОШИБКА] Приложение завершилось с ошибкой
    pause
    exit /b 1
)

