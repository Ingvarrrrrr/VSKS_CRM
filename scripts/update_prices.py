#!/usr/bin/env python3
import csv
import psycopg2
import sys
import os
from decimal import Decimal

# Настройки подключения к базе данных
DB_HOST = "localhost"
DB_NAME = "vsks_crm"
DB_USER = "vsks_user"
DB_PASSWORD = "vsks_password"

# Путь к CSV файлу
CSV_PATH = "/tmp/products_technical_specifications.csv"

def clean_price(price_str):
    """Очистка строки цены от лишних символов и преобразование в Decimal"""
    if not price_str:
        return None
    
    # Удаляем пробелы, заменяем запятые на точки
    price_str = str(price_str).strip().replace(',', '.').replace(' ', '')
    
    # Удаляем всё, кроме цифр и точки
    cleaned = ''.join(c for c in price_str if c.isdigit() or c == '.')
    
    if not cleaned:
        return None
    
    try:
        # Преобразуем в Decimal с округлением до 2 знаков
        return Decimal(cleaned).quantize(Decimal('0.01'))
    except:
        return None

def update_prices():
    """Обновление цен товаров из CSV файла"""
    print(f"Чтение CSV файла: {CSV_PATH}")
    
    if not os.path.exists(CSV_PATH):
        print(f"Файл {CSV_PATH} не найден!")
        return
    
    # Подключение к базе данных
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cursor = conn.cursor()
        print("Подключение к базе данных установлено")
    except Exception as e:
        print(f"Ошибка подключения к базе данных: {e}")
        return
    
    # Чтение CSV файла
    updated_count = 0
    not_found_count = 0
    error_count = 0
    
    with open(CSV_PATH, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',')
        
        # Определяем индекс столбца с ценой
        # Пробуем разные возможные названия столбцов
        price_columns = ['Цена за ед.', 'Цена', 'Цена 1 (руб)', 'Цена за ед']
        price_column = None
        
        for col in price_columns:
            if col in reader.fieldnames:
                price_column = col
                break
        
        if not price_column:
            print(f"Столбец с ценой не найден! Доступные столбцы: {reader.fieldnames}")
            return
        
        print(f"Используем столбец с ценой: {price_column}")
        
        for row_num, row in enumerate(reader, 1):
            try:
                product_name = row.get('Наименование', '').strip()
                if not product_name:
                    continue
                
                # Очищаем цену
                raw_price = row.get(price_column, '')
                price = clean_price(raw_price)
                
                if price is None:
                    # Пробуем другие столбцы с ценами
                    for alt_col in ['Цена', 'Цена 1 (руб)', 'Цена 2 (руб)', 'Цена 3 (руб)']:
                        if alt_col in row:
                            price = clean_price(row[alt_col])
                            if price is not None:
                                break
                
                if price is None:
                    # Пропускаем товары без цены
                    continue
                
                # Ищем товар в базе по названию (точное совпадение)
                cursor.execute(
                    "SELECT id FROM products WHERE name = %s LIMIT 1",
                    (product_name,)
                )
                
                result = cursor.fetchone()
                
                if result:
                    product_id = result[0]
                    # Обновляем цену
                    cursor.execute(
                        "UPDATE products SET price = %s WHERE id = %s",
                        (price, product_id)
                    )
                    updated_count += 1
                    
                    if updated_count % 100 == 0:
                        print(f"Обработано {updated_count} товаров...")
                else:
                    # Пробуем найти по частичному совпадению
                    cursor.execute(
                        "SELECT id FROM products WHERE name ILIKE %s LIMIT 1",
                        (f'%{product_name[:30]}%',)
                    )
                    
                    result = cursor.fetchone()
                    
                    if result:
                        product_id = result[0]
                        cursor.execute(
                            "UPDATE products SET price = %s WHERE id = %s",
                            (price, product_id)
                        )
                        updated_count += 1
                    else:
                        not_found_count += 1
                        
            except Exception as e:
                error_count += 1
                if error_count <= 5:  # Выводим только первые 5 ошибок
                    print(f"Ошибка в строке {row_num}: {e}")
    
    # Применяем изменения
    conn.commit()
    
    print(f"\nРезультаты обновления цен:")
    print(f"  Обновлено товаров: {updated_count}")
    print(f"  Товаров не найдено: {not_found_count}")
    print(f"  Ошибок обработки: {error_count}")
    
    # Проверяем сколько товаров теперь имеют цену
    cursor.execute("SELECT COUNT(*) FROM products WHERE price IS NOT NULL")
    total_with_price = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM products")
    total_products = cursor.fetchone()[0]
    
    print(f"\nВсего товаров в базе: {total_products}")
    print(f"Товаров с ценой: {total_with_price} ({total_with_price/total_products*100:.1f}%)")
    
    # Закрываем соединение
    cursor.close()
    conn.close()

if __name__ == "__main__":
    update_prices()