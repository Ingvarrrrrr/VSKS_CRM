@echo off
chcp 65001 >nul
echo ========================================
echo   Установка CRM Системы
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

echo [ИНФО] Установка зависимостей...
%PYTHON_CMD% -m pip install --upgrade pip
%PYTHON_CMD% -m pip install -r requirements.txt

if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить зависимости
    pause
    exit /b 1
)

echo.
echo [ИНФО] Создание структуры базы данных...
%PYTHON_CMD% create_excel_structure.py

if errorlevel 1 (
    echo [ОШИБКА] Не удалось создать структуру базы данных
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Установка завершена успешно!
echo ========================================
echo.
echo Для запуска приложения используйте: run.bat
echo Или: python main.py
echo.
pause

