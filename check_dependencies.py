"""
Скрипт для проверки и установки зависимостей
"""

import sys
import subprocess

def check_and_install():
    """Проверка и установка зависимостей"""
    
    required_packages = [
        'openpyxl',
        'pandas',
        'PyQt6',
        'python-docx',
        'xlrd'
    ]
    
    missing_packages = []
    
    print("Проверка зависимостей...")
    print("-" * 50)
    
    for package in required_packages:
        try:
            if package == 'PyQt6':
                __import__('PyQt6.QtWidgets')
            elif package == 'python-docx':
                __import__('docx')  # python-docx импортируется как docx
            else:
                __import__(package)
            print(f"[OK] {package} установлен")
        except ImportError:
            print(f"[X] {package} не найден")
            missing_packages.append(package)
    
    print("-" * 50)
    
    if missing_packages:
        print(f"\nУстановка отсутствующих пакетов: {', '.join(missing_packages)}")
        try:
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install', '-q'
            ] + missing_packages)
            print("\n[OK] Все зависимости установлены!")
            return True
        except subprocess.CalledProcessError:
            print("\n[ОШИБКА] Не удалось установить зависимости")
            print("Попробуйте вручную: pip install -r requirements.txt")
            return False
    else:
        print("\n[OK] Все зависимости установлены!")
        return True

if __name__ == '__main__':
    if check_and_install():
        print("\nМожно запускать приложение: python main.py")
    else:
        sys.exit(1)

