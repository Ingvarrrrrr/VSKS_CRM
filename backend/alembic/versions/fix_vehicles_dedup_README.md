# fix_vehicles_dedup — инструкция по применению

## Что делает миграция

Устраняет дублирование записей ТС в таблице `vehicles`, возникшее из-за расхождения формата `plate` между старыми записями (id 1–39, plate с пробелами, без VIN) и записями seed Голичкова (plate без пробелов, с VIN).

**7 групп VIN-дублей:**

| VIN | Дублирующие id | Canonical id |
|-----|---------------|-------------|
| X8956584480AD4033 | 11, 14, 312, 314 | **11** (4 копии, Митсубиси Делика) |
| X8956584490AD4082 | 13, 313 | **13** |
| VF77DNFRCCJ641603 | 23, 335 | **23** |
| XTT316300P1015643 | 8, 305 | **8** |
| XTT316300P1023047 | 9, 306 | **9** |
| XTT390995P1205016 | 10, 308 | **10** |
| XTC43101M0039560 | 15, 315 | **15** |

**2 группы plate-дублей (без VIN):**

| Plate (норм.) | Дублирующие id | Canonical id |
|--------------|---------------|-------------|
| К618ВС797 | 16, 316 | **16** |
| Н429ВВ977 | 17, 317 | **17** |

**Итого: 75 → ~67 ТС** (удаляется 8 записей: 3 из четвёрки Делики + 6 пар = 9 дублей).

Шаги миграции:
1. Нормализация `plate` (убрать пробелы, UPPER) — делает дубли видимыми
2. Построение mapping `duplicate_id → canonical_id` во временную таблицу
3. Перевод FK во всех 12 дочерних таблицах на canonical-id
4. Удаление записей-дубликатов из `vehicles`
5. Создание `UNIQUE INDEX vehicles_vin_unique_partial` — предотвращает новые VIN-дубли
6. Проверочные SELECT (ожидаем 0 дублей по VIN и plate)

---

## Backup ДО применения

Всегда делать backup перед запуском:

```bash
docker exec vsks_crm-db-1 pg_dump -U vsks -d vsks_crm > vehicles_backup_$(date +%Y-%m-%d).sql
```

Или конкретно таблицы vehicles и связанных:

```bash
docker exec vsks_crm-db-1 pg_dump -U vsks -d vsks_crm \
  -t vehicles -t vehicle_repairs -t vehicle_odometer \
  -t fuel_logs -t trips -t vehicle_fines -t vehicle_attachments \
  -t fleet_documents -t vehicle_field_history -t vehicle_transfer_history \
  -t checklists -t incidents -t purchases \
  > vehicles_and_related_backup_$(date +%Y-%m-%d).sql
```

---

## Как применить локально

```bash
# Вариант 1: через stdin (рекомендуется)
docker exec -i vsks_crm-db-1 psql -U vsks -d vsks_crm \
  < backend/alembic/versions/fix_vehicles_dedup.sql

# Вариант 2: скопировать файл в контейнер и выполнить
docker cp backend/alembic/versions/fix_vehicles_dedup.sql vsks_crm-db-1:/tmp/
docker exec vsks_crm-db-1 psql -U vsks -d vsks_crm \
  -f /tmp/fix_vehicles_dedup.sql
```

Скрипт **идемпотентен**: повторный запуск ничего не удалит и не сломает.

---

## Ожидаемый результат

После выполнения скрипт выведет три строки проверки:

```
     check_name          | cnt
-------------------------+-----
 vin_duplicates_remaining|   0
 plate_duplicates_remaining| 0
 total_vehicles_after    |  67
```

Число 67 может незначительно отличаться, если в БД уже были другие изменения.

---

## Rollback

Миграция содержит `DELETE` — **это необратимая операция**. Downgrade-скрипта нет.

Для восстановления используйте backup, сделанный до применения:

```bash
# Полное восстановление БД
docker exec -i vsks_crm-db-1 psql -U vsks -d vsks_crm < vehicles_backup_YYYY-MM-DD.sql

# Если нужно восстановить только таблицу vehicles (осторожно — FK-конфликты):
# 1. Удалить partial unique index
docker exec vsks_crm-db-1 psql -U vsks -d vsks_crm \
  -c "DROP INDEX IF EXISTS vehicles_vin_unique_partial;"
# 2. Восстановить из бэкапа только vehicles
docker exec -i vsks_crm-db-1 psql -U vsks -d vsks_crm < vehicles_backup_YYYY-MM-DD.sql
```

---

## Pitfalls / известные нюансы

- **Слияние дочерних данных** — после мерджа у canonical-id будут все repair, trip, fuel_log, odometer и т.д. от обоих дубликатов. Это **ожидаемое поведение**: суммарная история ТС.
- **vehicle_odometer UNIQUE(vehicle_id, date)** — если дубль и canonical имели одометр за одну и ту же дату, строка дубля **удаляется** (остаётся запись canonical). Обработано в шаге 3.10.
- **purchases.vehicle_id** — nullable (SET NULL при каскаде), но мёрджится явно в шаге 3.5.
- **vehicle_fines** — штрафы переезжают на canonical. Если штраф был на дубле — теперь числится на основном ТС.
- **trips (путевые листы)** — все путевые листы дубля переходят к canonical. Водитель в путевом листе не меняется.
- **Partial unique index** создаётся с `IF NOT EXISTS` — безопасно при повторном запуске.
