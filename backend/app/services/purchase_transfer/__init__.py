"""Копирование/слияние закупок между субсидиями (POST /api/purchase-transfer/*).

ПРАВИЛО №5 — каждая ответственность в своём файле:
  match.py            — ключ закупки + классификация (та же пара / только сумма / нет пары).
  copy_one.py         — copy_to_subsidy: создать копию закупки(ок) в другой субсидии.
  merge_into.py       — merge_into: «это та же закупка» — дополнить существующую.
  doc_transfer.py     — файлы/чеки (перенесено из scripts/fadm_sheet_load/files_copy.py).
  people_transfer.py  — исполнитель/инициатор/участники.
  comments_transfer.py — комментарии.

ПРАВИЛО №6 — ничего не считается второй раз:
  - «эффективная сумма» — app.services.purchase_amounts.load_purchase_amounts;
  - копирование закупок целиком (договор/позиции/чеки/платежи/аллокации) —
    app.services.subsidy_copy.copy_purchases.copy_purchases;
  - сопоставление категорий/плановых позиций двух субсидий по имени —
    app.services.subsidy_copy.copy_into_existing (build_category_map/build_planned_item_map);
  - категория «Не определена» — app.services.feo_unallocated.get_or_create_unallocated;
  - проверка «субсидия утверждена» — app.services.subsidy_draft_guard.
    assert_subsidy_approved_for_binding.

scripts/fadm_sheet_load/sheet_v2_enrich.py и pair_old_to_target.py переведены
на импорт ключа/пар и переноса людей/комментариев/документов отсюда — второй
копии этой логики в scripts больше нет.
"""
